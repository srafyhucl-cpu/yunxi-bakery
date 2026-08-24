"""有赞客户迁移审计脚本。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.database import close_db, init_db  # noqa: E402
from app.repository.customer_master_repo import CustomerMasterRepo  # noqa: E402
from app.service.customer import CustomerImportService, CustomerMasterService  # noqa: E402

UTF8_BOM = b"\xef\xbb\xbf"
OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
DEFAULT_CUSTOMER_CSV = ROOT_DIR / "docs" / "有赞导出" / "客户数据_0002000408539943.csv"
DEFAULT_ORDERS_CSV = ROOT_DIR / "docs" / "有赞导出" / "订单数据.csv"
DEFAULT_IMPORT_REPORT = ROOT_DIR / "reports" / "youzan-customer-import-{timestamp}.json"
VALID_PHONE_LENGTH = 11
VALID_PHONE_PREFIX = "1"
HIGH_MISSING_PHONE_RATE = 0.3
MEDIUM_MISSING_PHONE_RATE = 0.1
LOW_AVAILABILITY_RATE = 0.5
MEDIUM_AVAILABILITY_RATE = 0.8
EMPTY_LIKE_VALUES = frozenset({"", "?", "—", "——", "N/A", "n/a", "null", "None"})

CUSTOMER_REQUIRED_FIELDS = (
    "客户姓名",
    "客户昵称",
    "客户手机号",
    "客户生日",
    "客户性别",
    "标签",
    "是否会员",
    "成长值",
    "客户储值余额",
    "上次消费时间",
    "来源渠道",
    "来源方式",
    "成为客户时间",
    "微信地域",
)
ORDER_REQUIRED_FIELDS = (
    "订单号",
    "订单创建时间",
    "买家昵称",
    "买家是否会员",
    "买家手机号",
    "交易成功时间",
    "订单实收金额",
    "销售渠道",
    "订单来源",
)
METRIC_FIELDNAMES = (
    "metric_key",
    "metric_name",
    "metric_value",
    "risk_level",
    "notes",
)
ISSUE_FIELDNAMES = (
    "source_record_id",
    "customer_name",
    "customer_nickname",
    "raw_phone",
    "normalized_phone",
    "issue_type",
    "risk_level",
    "suggested_action",
    "matched_order_phone",
    "notes",
)
BUCKET_FIELDNAMES = (
    "source_record_id",
    "normalized_phone",
    "proposed_bucket",
    "confidence_level",
    "conflict_flags",
    "recommended_customer_action",
)


@dataclass(frozen=True)
class CustomerRecord:
    """客户导出行的标准化结果。"""

    source_record_id: str
    customer_name: str
    customer_nickname: str
    raw_phone: str
    normalized_phone: str
    display_name_candidate: str
    birthday: str
    gender: str
    wechat_region: str
    first_seen_at_candidate: str
    last_seen_at_candidate: str
    member_flag: str
    growth_value: str
    balance_value: str
    tag_value: str
    source_channel: str
    source_method: str


@dataclass(frozen=True)
class OrderRecord:
    """订单导出行的标准化结果。"""

    order_id: str
    buyer_nickname: str
    raw_buyer_phone: str
    normalized_buyer_phone: str


@dataclass(frozen=True)
class DuplicateGroup:
    """同手机号客户组的冲突分析。"""

    phone: str
    record_ids: tuple[str, ...]
    has_name_conflict: bool
    has_membership_conflict: bool
    has_source_conflict: bool

    def conflict_flags(self) -> list[str]:
        flags: list[str] = []
        if self.has_name_conflict:
            flags.append("name_conflict_same_phone")
        if self.has_membership_conflict:
            flags.append("membership_conflict_same_phone")
        if self.has_source_conflict:
            flags.append("source_conflict_same_phone")
        return flags


@dataclass(frozen=True)
class IssueRow:
    """客户问题行。"""

    source_record_id: str
    customer_name: str
    customer_nickname: str
    raw_phone: str
    normalized_phone: str
    issue_type: str
    risk_level: str
    suggested_action: str
    matched_order_phone: str
    notes: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source_record_id": self.source_record_id,
            "customer_name": self.customer_name,
            "customer_nickname": self.customer_nickname,
            "raw_phone": self.raw_phone,
            "normalized_phone": self.normalized_phone,
            "issue_type": self.issue_type,
            "risk_level": self.risk_level,
            "suggested_action": self.suggested_action,
            "matched_order_phone": self.matched_order_phone,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class BucketRow:
    """客户分流行。"""

    source_record_id: str
    normalized_phone: str
    proposed_bucket: str
    confidence_level: str
    conflict_flags: str
    recommended_customer_action: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source_record_id": self.source_record_id,
            "normalized_phone": self.normalized_phone,
            "proposed_bucket": self.proposed_bucket,
            "confidence_level": self.confidence_level,
            "conflict_flags": self.conflict_flags,
            "recommended_customer_action": self.recommended_customer_action,
        }


@dataclass(frozen=True)
class MetricRow:
    """汇总指标行。"""

    metric_key: str
    metric_name: str
    metric_value: str
    risk_level: str
    notes: str

    def to_dict(self) -> dict[str, str]:
        return {
            "metric_key": self.metric_key,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "risk_level": self.risk_level,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class AuditArtifacts:
    """审计输出集合。"""

    summary: dict[str, object]
    metrics: list[MetricRow]
    issues: list[IssueRow]
    buckets: list[BucketRow]


@dataclass(frozen=True)
class ImportRow:
    """客户试导入结果行。"""

    source_record_id: str
    customer_id: str
    identity_link_id: str
    snapshot_id: str
    merge_review_id: str
    resolved_bucket: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source_record_id": self.source_record_id,
            "customer_id": self.customer_id,
            "identity_link_id": self.identity_link_id,
            "snapshot_id": self.snapshot_id,
            "merge_review_id": self.merge_review_id,
            "resolved_bucket": self.resolved_bucket,
            "action": self.action,
        }


@dataclass(frozen=True)
class ImportArtifacts:
    """客户试导入输出集合。"""

    tenant_id: str
    source_batch_id: str
    total_records: int
    imported_rows: list[ImportRow]
    bucket_summary: dict[str, int]
    actions_summary: dict[str, int]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Youzan customer migration")
    parser.add_argument(
        "--customer-csv",
        default=str(DEFAULT_CUSTOMER_CSV),
        help="有赞客户导出 CSV 路径。",
    )
    parser.add_argument(
        "--orders-csv",
        default=str(DEFAULT_ORDERS_CSV),
        help="有赞订单导出 CSV 路径。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出机器可读 JSON。",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="配合 --json 使用，将汇总 JSON 写入指定文件，支持 {timestamp}。",
    )
    parser.add_argument(
        "--metrics-output",
        default=None,
        help="将汇总指标表写入 CSV，支持 {timestamp}。",
    )
    parser.add_argument(
        "--issues-output",
        default=None,
        help="将客户问题表写入 CSV，支持 {timestamp}。",
    )
    parser.add_argument(
        "--buckets-output",
        default=None,
        help="将客户分流表写入 CSV，支持 {timestamp}。",
    )
    parser.add_argument(
        "--apply-import",
        action="store_true",
        help="按审计结果试导入 customer master v1 四表。",
    )
    parser.add_argument(
        "--db-path",
        default=":memory:",
        help="试导入目标 SQLite 路径，默认 :memory:。",
    )
    parser.add_argument(
        "--tenant-id",
        default="yunxi",
        help="试导入租户 ID，默认 yunxi。",
    )
    parser.add_argument(
        "--source-batch-id",
        default="",
        help="试导入批次 ID；不传则自动按时间生成。",
    )
    parser.add_argument(
        "--import-output",
        default=str(DEFAULT_IMPORT_REPORT),
        help="配合 --apply-import 输出试导入 JSON 报告，支持 {timestamp}。",
    )
    return parser.parse_args(argv)


def resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT_DIR / path


def expand_output_path(output_path_value: str) -> Path:
    timestamp = datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
    expanded_value = output_path_value.replace(OUTPUT_TIMESTAMP_PLACEHOLDER, timestamp)
    return Path(expanded_value)


def ensure_output_path_available(output_path_value: str) -> Path:
    output_path = expand_output_path(output_path_value)
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    return output_path


def write_json_report(output_path: Path, json_bytes: bytes) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(UTF8_BOM + json_bytes)


def write_csv_report(
    output_path: Path,
    fieldnames: tuple[str, ...],
    rows: list[dict[str, str]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize_value(raw_value: str | None) -> str:
    value = (raw_value or "").strip()
    if value in EMPTY_LIKE_VALUES:
        return ""
    return value


def normalize_phone(raw_value: str | None) -> str:
    value = normalize_value(raw_value)
    if not value or "*" in value:
        return ""
    digits_only = "".join(ch for ch in value if ch.isdigit())
    if len(digits_only) != VALID_PHONE_LENGTH:
        return ""
    if not digits_only.startswith(VALID_PHONE_PREFIX):
        return ""
    return digits_only


def normalize_display_name(*raw_values: str | None) -> str:
    for raw_value in raw_values:
        value = normalize_value(raw_value)
        if value:
            return value
    return ""


def read_csv_rows(path: Path, required_fields: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = tuple(reader.fieldnames or ())
        missing_fields = [field for field in required_fields if field not in headers]
        if missing_fields:
            missing_text = ", ".join(missing_fields)
            raise ValueError(f"CSV 缺少必需字段: {missing_text}")
        return [dict(row) for row in reader]


def build_customer_records(customer_rows: list[dict[str, str]]) -> list[CustomerRecord]:
    records: list[CustomerRecord] = []
    for row_index, row in enumerate(customer_rows, start=1):
        records.append(
            CustomerRecord(
                source_record_id=f"customer-row-{row_index}",
                customer_name=normalize_value(row.get("客户姓名")),
                customer_nickname=normalize_value(row.get("客户昵称")),
                raw_phone=normalize_value(row.get("客户手机号")),
                normalized_phone=normalize_phone(row.get("客户手机号")),
                display_name_candidate=normalize_display_name(
                    row.get("客户姓名"),
                    row.get("客户昵称"),
                ),
                birthday=normalize_value(row.get("客户生日")),
                gender=normalize_value(row.get("客户性别")),
                wechat_region=normalize_value(row.get("微信地域")),
                first_seen_at_candidate=normalize_value(row.get("成为客户时间")),
                last_seen_at_candidate=normalize_value(row.get("上次消费时间")),
                member_flag=normalize_value(row.get("是否会员")),
                growth_value=normalize_value(row.get("成长值")),
                balance_value=normalize_value(row.get("客户储值余额")),
                tag_value=normalize_value(row.get("标签")),
                source_channel=normalize_value(row.get("来源渠道")),
                source_method=normalize_value(row.get("来源方式")),
            )
        )
    return records


def build_order_records(order_rows: list[dict[str, str]]) -> list[OrderRecord]:
    records: list[OrderRecord] = []
    for row in order_rows:
        records.append(
            OrderRecord(
                order_id=normalize_value(row.get("订单号")),
                buyer_nickname=normalize_display_name(row.get("买家昵称")),
                raw_buyer_phone=normalize_value(row.get("买家手机号")),
                normalized_buyer_phone=normalize_phone(row.get("买家手机号")),
            )
        )
    return records


def build_customer_row_map(
    customer_rows: list[dict[str, str]],
) -> dict[str, dict[str, str]]:
    return {
        f"customer-row-{row_index}": dict(row)
        for row_index, row in enumerate(customer_rows, start=1)
    }


def build_duplicate_groups(
    customer_records: list[CustomerRecord],
) -> dict[str, DuplicateGroup]:
    records_by_phone: dict[str, list[CustomerRecord]] = defaultdict(list)
    for record in customer_records:
        if record.normalized_phone:
            records_by_phone[record.normalized_phone].append(record)

    duplicate_groups: dict[str, DuplicateGroup] = {}
    for phone, grouped_records in records_by_phone.items():
        if len(grouped_records) <= 1:
            continue
        duplicate_groups[phone] = DuplicateGroup(
            phone=phone,
            record_ids=tuple(record.source_record_id for record in grouped_records),
            has_name_conflict=_has_multiple_values(
                record.display_name_candidate for record in grouped_records
            ),
            has_membership_conflict=_has_multiple_values(
                record.member_flag for record in grouped_records
            ),
            has_source_conflict=_has_multiple_values(
                record.source_channel for record in grouped_records
            ),
        )
    return duplicate_groups


def _has_multiple_values(values: object) -> bool:
    distinct_values = {value for value in values if value}
    return len(distinct_values) > 1


def build_order_nickname_phone_map(order_records: list[OrderRecord]) -> dict[str, str]:
    phones_by_name: dict[str, set[str]] = defaultdict(set)
    for order in order_records:
        if order.buyer_nickname and order.normalized_buyer_phone:
            phones_by_name[order.buyer_nickname].add(order.normalized_buyer_phone)
    return {
        nickname: next(iter(phone_values))
        for nickname, phone_values in phones_by_name.items()
        if len(phone_values) == 1
    }


def build_bucket_row(
    record: CustomerRecord,
    duplicate_group: DuplicateGroup | None,
    matched_order_phone: str,
) -> BucketRow:
    if duplicate_group is not None:
        return BucketRow(
            source_record_id=record.source_record_id,
            normalized_phone=record.normalized_phone,
            proposed_bucket="pending_review",
            confidence_level="low",
            conflict_flags="|".join(duplicate_group.conflict_flags()),
            recommended_customer_action="人工复核同手机号客户，暂不自动并人",
        )
    if record.normalized_phone:
        return BucketRow(
            source_record_id=record.source_record_id,
            normalized_phone=record.normalized_phone,
            proposed_bucket="auto_merge",
            confidence_level="high",
            conflict_flags="",
            recommended_customer_action="自动挂接到唯一手机号主档",
        )
    suggested_action = "创建弱身份主档，等待后续身份补强"
    confidence_level = "low"
    if matched_order_phone:
        suggested_action = "创建弱身份主档，并参考订单手机号人工复核"
        confidence_level = "medium"
    return BucketRow(
        source_record_id=record.source_record_id,
        normalized_phone="",
        proposed_bucket="new_master",
        confidence_level=confidence_level,
        conflict_flags="",
        recommended_customer_action=suggested_action,
    )


def build_issue_row(
    record: CustomerRecord,
    duplicate_group: DuplicateGroup | None,
    matched_order_phone: str,
) -> IssueRow | None:
    if duplicate_group is not None:
        flags_text = ", ".join(duplicate_group.conflict_flags()) or "duplicate_phone"
        return IssueRow(
            source_record_id=record.source_record_id,
            customer_name=record.customer_name,
            customer_nickname=record.customer_nickname,
            raw_phone=record.raw_phone,
            normalized_phone=record.normalized_phone,
            issue_type="duplicate_phone",
            risk_level="high",
            suggested_action="加入 pending_review，人工复核后再决定是否合并",
            matched_order_phone="",
            notes=flags_text,
        )
    if record.raw_phone and not record.normalized_phone:
        return IssueRow(
            source_record_id=record.source_record_id,
            customer_name=record.customer_name,
            customer_nickname=record.customer_nickname,
            raw_phone=record.raw_phone,
            normalized_phone="",
            issue_type="invalid_phone",
            risk_level="high",
            suggested_action="修正手机号格式后再参与自动归并",
            matched_order_phone="",
            notes="原始手机号存在但标准化失败",
        )
    if not record.normalized_phone:
        notes = "缺少有效手机号"
        if matched_order_phone:
            notes = f"{notes}; 订单侧存在可参考手机号 {matched_order_phone}"
        return IssueRow(
            source_record_id=record.source_record_id,
            customer_name=record.customer_name,
            customer_nickname=record.customer_nickname,
            raw_phone=record.raw_phone,
            normalized_phone="",
            issue_type="missing_phone",
            risk_level="medium",
            suggested_action="先建弱身份主档，后续通过企微或订单补强",
            matched_order_phone=matched_order_phone,
            notes=notes,
        )
    return None


def calculate_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def build_metric_rows(summary: dict[str, object]) -> list[MetricRow]:
    return [
        _metric_row(
            "total_customers",
            "客户总数",
            str(summary["total_customers"]),
            "low",
            "客户表总行数",
        ),
        _metric_row(
            "valid_phone_rate",
            "有效手机号占比",
            str(summary["valid_phone_rate"]),
            _rate_risk_level(float(summary["valid_phone_rate"])),
            "首版自动归并的基础指标",
        ),
        _metric_row(
            "duplicate_phone_customer_count",
            "重复手机号客户数",
            str(summary["duplicate_phone_customer_count"]),
            _non_zero_risk_level(int(summary["duplicate_phone_customer_count"])),
            "进入 pending_review 的高风险客户规模",
        ),
        _metric_row(
            "invalid_phone_count",
            "异常手机号客户数",
            str(summary["invalid_phone_count"]),
            _non_zero_risk_level(int(summary["invalid_phone_count"])),
            "原始手机号存在但标准化失败",
        ),
        _metric_row(
            "auto_merge_customer_count",
            "可自动归并客户数",
            str(summary["auto_merge_customer_count"]),
            "low",
            "可直接按唯一手机号归并",
        ),
        _metric_row(
            "new_master_customer_count",
            "弱身份主档客户数",
            str(summary["new_master_customer_count"]),
            "medium" if int(summary["new_master_customer_count"]) > 0 else "low",
            "缺少有效手机号或只能等待后续补强",
        ),
        _metric_row(
            "pending_review_customer_count",
            "人工复核客户数",
            str(summary["pending_review_customer_count"]),
            _non_zero_risk_level(int(summary["pending_review_customer_count"])),
            "同手机号冲突或高风险记录",
        ),
        _metric_row(
            "orders_phone_match_customer",
            "订单手机号命中客户表订单数",
            str(summary["orders_phone_match_customer"]),
            "low",
            "订单侧对客户手机号的支撑程度",
        ),
        _metric_row(
            "customers_missing_phone_but_order_matchable",
            "无手机号但订单侧可补强客户数",
            str(summary["customers_missing_phone_but_order_matchable"]),
            "medium"
            if int(summary["customers_missing_phone_but_order_matchable"]) > 0
            else "low",
            "可作为人工复核候选",
        ),
        _metric_row(
            "display_name_available_rate",
            "称呼候选可用率",
            str(summary["display_name_available_rate"]),
            _availability_risk_level(float(summary["display_name_available_rate"])),
            "决定 display_name 是否必须可空",
        ),
        _metric_row(
            "birthday_available_rate",
            "生日可用率",
            str(summary["birthday_available_rate"]),
            _availability_risk_level(float(summary["birthday_available_rate"])),
            "主档候选辅助字段质量",
        ),
        _metric_row(
            "source_channel_distribution",
            "来源渠道分布",
            json.dumps(summary["source_channel_distribution"], ensure_ascii=False),
            "low",
            "来源渠道快照分布",
        ),
    ]


def _metric_row(
    metric_key: str,
    metric_name: str,
    metric_value: str,
    risk_level: str,
    notes: str,
) -> MetricRow:
    return MetricRow(metric_key, metric_name, metric_value, risk_level, notes)


def _rate_risk_level(rate_value: float) -> str:
    if rate_value < HIGH_MISSING_PHONE_RATE:
        return "high"
    if rate_value < MEDIUM_MISSING_PHONE_RATE:
        return "medium"
    return "low"


def _non_zero_risk_level(metric_value: int) -> str:
    return "high" if metric_value > 0 else "low"


def _availability_risk_level(rate_value: float) -> str:
    if rate_value < LOW_AVAILABILITY_RATE:
        return "medium"
    if rate_value < MEDIUM_AVAILABILITY_RATE:
        return "low"
    return "low"


def run_audit(customer_csv_path: Path, orders_csv_path: Path) -> AuditArtifacts:
    customer_rows = read_csv_rows(customer_csv_path, CUSTOMER_REQUIRED_FIELDS)
    order_rows = read_csv_rows(orders_csv_path, ORDER_REQUIRED_FIELDS)
    customer_records = build_customer_records(customer_rows)
    order_records = build_order_records(order_rows)
    duplicate_groups = build_duplicate_groups(customer_records)
    nickname_phone_map = build_order_nickname_phone_map(order_records)
    valid_customer_phones = {
        record.normalized_phone
        for record in customer_records
        if record.normalized_phone
    }
    valid_order_phone_count = sum(
        1 for record in order_records if record.normalized_buyer_phone
    )

    buckets: list[BucketRow] = []
    issues: list[IssueRow] = []
    for record in customer_records:
        duplicate_group = duplicate_groups.get(record.normalized_phone)
        matched_order_phone = ""
        if not record.normalized_phone and record.display_name_candidate:
            matched_order_phone = nickname_phone_map.get(
                record.display_name_candidate, ""
            )
        bucket_row = build_bucket_row(record, duplicate_group, matched_order_phone)
        buckets.append(bucket_row)
        issue_row = build_issue_row(record, duplicate_group, matched_order_phone)
        if issue_row is not None:
            issues.append(issue_row)

    source_channel_distribution = dict(
        Counter(record.source_channel or "UNKNOWN" for record in customer_records)
    )
    duplicate_phone_customer_count = sum(
        len(group.record_ids) for group in duplicate_groups.values()
    )
    summary = {
        "total_customers": len(customer_records),
        "customers_with_phone": sum(
            1 for record in customer_records if record.normalized_phone
        ),
        "customers_without_phone": sum(
            1 for record in customer_records if not record.normalized_phone
        ),
        "valid_phone_rate": calculate_rate(
            sum(1 for record in customer_records if record.normalized_phone),
            len(customer_records),
        ),
        "unique_phone_count": len(valid_customer_phones),
        "duplicate_phone_customer_count": duplicate_phone_customer_count,
        "duplicate_phone_group_count": len(duplicate_groups),
        "invalid_phone_count": sum(
            1
            for record in customer_records
            if record.raw_phone and not record.normalized_phone
        ),
        "auto_merge_customer_count": sum(
            1 for bucket in buckets if bucket.proposed_bucket == "auto_merge"
        ),
        "new_master_customer_count": sum(
            1 for bucket in buckets if bucket.proposed_bucket == "new_master"
        ),
        "pending_review_customer_count": sum(
            1 for bucket in buckets if bucket.proposed_bucket == "pending_review"
        ),
        "orders_with_buyer_phone": valid_order_phone_count,
        "orders_phone_match_customer": sum(
            1
            for record in order_records
            if record.normalized_buyer_phone in valid_customer_phones
        ),
        "customers_missing_phone_but_order_matchable": sum(
            1
            for issue in issues
            if issue.issue_type == "missing_phone" and issue.matched_order_phone
        ),
        "display_name_available_rate": calculate_rate(
            sum(1 for record in customer_records if record.display_name_candidate),
            len(customer_records),
        ),
        "birthday_available_rate": calculate_rate(
            sum(1 for record in customer_records if record.birthday),
            len(customer_records),
        ),
        "gender_available_rate": calculate_rate(
            sum(1 for record in customer_records if record.gender),
            len(customer_records),
        ),
        "wechat_region_available_rate": calculate_rate(
            sum(1 for record in customer_records if record.wechat_region),
            len(customer_records),
        ),
        "first_seen_at_available_rate": calculate_rate(
            sum(1 for record in customer_records if record.first_seen_at_candidate),
            len(customer_records),
        ),
        "last_seen_at_available_rate": calculate_rate(
            sum(1 for record in customer_records if record.last_seen_at_candidate),
            len(customer_records),
        ),
        "tag_non_empty_rate": calculate_rate(
            sum(1 for record in customer_records if record.tag_value),
            len(customer_records),
        ),
        "member_flag_non_empty_rate": calculate_rate(
            sum(1 for record in customer_records if record.member_flag),
            len(customer_records),
        ),
        "growth_value_non_empty_rate": calculate_rate(
            sum(1 for record in customer_records if record.growth_value),
            len(customer_records),
        ),
        "balance_non_empty_rate": calculate_rate(
            sum(1 for record in customer_records if record.balance_value),
            len(customer_records),
        ),
        "same_phone_name_conflict_count": sum(
            len(group.record_ids)
            for group in duplicate_groups.values()
            if group.has_name_conflict
        ),
        "same_phone_membership_conflict_count": sum(
            len(group.record_ids)
            for group in duplicate_groups.values()
            if group.has_membership_conflict
        ),
        "same_phone_source_conflict_count": sum(
            len(group.record_ids)
            for group in duplicate_groups.values()
            if group.has_source_conflict
        ),
        "source_channel_distribution": source_channel_distribution,
    }
    metrics = build_metric_rows(summary)
    return AuditArtifacts(
        summary=summary, metrics=metrics, issues=issues, buckets=buckets
    )


def build_import_payloads(
    *,
    customer_rows: list[dict[str, str]],
    customer_records: list[CustomerRecord],
    audit_artifacts: AuditArtifacts,
    tenant_id: str,
    source_batch_id: str,
) -> list[dict[str, object]]:
    row_map = build_customer_row_map(customer_rows)
    bucket_map = {row.source_record_id: row for row in audit_artifacts.buckets}
    issue_map = {row.source_record_id: row for row in audit_artifacts.issues}
    payloads: list[dict[str, object]] = []
    for record in customer_records:
        bucket = bucket_map[record.source_record_id]
        issue = issue_map.get(record.source_record_id)
        raw_row = row_map[record.source_record_id]
        normalized_payload = {
            "source_record_id": record.source_record_id,
            "proposed_bucket": bucket.proposed_bucket,
            "primary_phone": record.normalized_phone,
            "display_name": record.display_name_candidate,
            "birthday": record.birthday,
            "gender": _normalize_gender(record.gender),
            "wechat_region": record.wechat_region,
            "first_seen_at": record.first_seen_at_candidate,
            "last_seen_at": record.last_seen_at_candidate,
            "source_channel": record.source_channel,
            "source_method": record.source_method,
            "member_flag": record.member_flag,
            "growth_value": record.growth_value,
            "balance_value": record.balance_value,
            "tag_value": record.tag_value,
            "matched_order_phone": issue.matched_order_phone if issue else "",
        }
        payloads.append(
            {
                "tenant_id": tenant_id,
                "source_record_id": record.source_record_id,
                "source_batch_id": source_batch_id,
                "proposed_bucket": bucket.proposed_bucket,
                "confidence_level": bucket.confidence_level,
                "source_system": "youzan",
                "source_channel": record.source_channel,
                "source_method": record.source_method,
                "primary_phone": record.normalized_phone,
                "display_name": record.display_name_candidate,
                "birthday": record.birthday,
                "gender": _normalize_gender(record.gender),
                "wechat_region": record.wechat_region,
                "first_seen_at": record.first_seen_at_candidate,
                "last_seen_at": record.last_seen_at_candidate,
                "source_label": record.source_channel or "有赞客户导出",
                "conflict_flags": tuple(
                    flag for flag in bucket.conflict_flags.split("|") if flag.strip()
                ),
                "matched_order_phone": issue.matched_order_phone if issue else "",
                "snapshot_payload": raw_row,
                "normalized_payload": normalized_payload,
            }
        )
    return payloads


def _normalize_gender(gender: str) -> str:
    if gender == "男":
        return "male"
    if gender == "女":
        return "female"
    if gender:
        return "other"
    return "unknown"


def default_source_batch_id() -> str:
    return "youzan-import-" + datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)


async def run_import(
    *,
    db_path_value: str,
    tenant_id: str,
    source_batch_id: str,
    customer_csv_path: Path,
    orders_csv_path: Path,
) -> ImportArtifacts:
    customer_rows = read_csv_rows(customer_csv_path, CUSTOMER_REQUIRED_FIELDS)
    order_rows = read_csv_rows(orders_csv_path, ORDER_REQUIRED_FIELDS)
    customer_records = build_customer_records(customer_rows)
    _ = build_order_records(order_rows)
    audit_artifacts = run_audit(customer_csv_path, orders_csv_path)
    payloads = build_import_payloads(
        customer_rows=customer_rows,
        customer_records=customer_records,
        audit_artifacts=audit_artifacts,
        tenant_id=tenant_id,
        source_batch_id=source_batch_id,
    )

    imported_rows: list[ImportRow] = []
    conn = await init_db(db_path_value)
    try:
        repo = CustomerMasterRepo(conn)
        service = CustomerImportService(repo, CustomerMasterService(repo))
        for payload_dict in payloads:
            result = await service.import_record(
                service_payload_from_dict(payload_dict)
            )
            imported_rows.append(
                ImportRow(
                    source_record_id=result.source_record_id,
                    customer_id=result.customer_id,
                    identity_link_id=result.identity_link_id or "",
                    snapshot_id=result.snapshot_id,
                    merge_review_id=result.merge_review_id or "",
                    resolved_bucket=result.resolved_bucket,
                    action=result.action,
                )
            )
    finally:
        await close_db(conn)
    return ImportArtifacts(
        tenant_id=tenant_id,
        source_batch_id=source_batch_id,
        total_records=len(imported_rows),
        imported_rows=imported_rows,
        bucket_summary=dict(Counter(row.resolved_bucket for row in imported_rows)),
        actions_summary=dict(Counter(row.action for row in imported_rows)),
    )


def service_payload_from_dict(payload_dict: dict[str, object]):
    from app.service.customer.importer import CustomerImportPayload

    return CustomerImportPayload(**payload_dict)


def build_json_report(
    artifacts: AuditArtifacts,
    customer_csv_path: Path,
    orders_csv_path: Path,
) -> dict[str, object]:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "status": "ready",
        "metadata": {
            "generated_at": generated_at,
            "project_root": str(ROOT_DIR),
            "customer_csv": str(customer_csv_path),
            "orders_csv": str(orders_csv_path),
        },
        "summary": artifacts.summary,
        "metrics": [row.to_dict() for row in artifacts.metrics],
        "issues_count": len(artifacts.issues),
        "buckets_count": len(artifacts.buckets),
    }


def build_import_json_report(
    artifacts: ImportArtifacts,
    *,
    db_path_value: str,
) -> dict[str, object]:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "status": "ready",
        "metadata": {
            "generated_at": generated_at,
            "project_root": str(ROOT_DIR),
            "database_path": db_path_value,
            "tenant_id": artifacts.tenant_id,
            "source_batch_id": artifacts.source_batch_id,
        },
        "summary": {
            "total_records": artifacts.total_records,
            "bucket_summary": artifacts.bucket_summary,
            "actions_summary": artifacts.actions_summary,
        },
        "rows": [row.to_dict() for row in artifacts.imported_rows],
    }


def print_report(artifacts: AuditArtifacts) -> None:
    summary = artifacts.summary
    print("Youzan customer migration audit")
    print(f"total_customers={summary['total_customers']}")
    print(f"customers_with_phone={summary['customers_with_phone']}")
    print(f"customers_without_phone={summary['customers_without_phone']}")
    print(f"valid_phone_rate={summary['valid_phone_rate']}")
    print(f"duplicate_phone_customer_count={summary['duplicate_phone_customer_count']}")
    print(f"invalid_phone_count={summary['invalid_phone_count']}")
    print(f"auto_merge_customer_count={summary['auto_merge_customer_count']}")
    print(f"new_master_customer_count={summary['new_master_customer_count']}")
    print(f"pending_review_customer_count={summary['pending_review_customer_count']}")
    print(
        "customers_missing_phone_but_order_matchable="
        + str(summary["customers_missing_phone_but_order_matchable"])
    )


def resolve_output_paths(args: argparse.Namespace) -> dict[str, Path | None]:
    resolved_paths: dict[str, Path | None] = {}
    for key in (
        "output",
        "metrics_output",
        "issues_output",
        "buckets_output",
        "import_output",
    ):
        path_value = getattr(args, key)
        if path_value is None:
            resolved_paths[key] = None
            continue
        if key == "import_output" and not args.apply_import:
            resolved_paths[key] = None
            continue
        resolved_paths[key] = ensure_output_path_available(path_value)
    return resolved_paths


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.output and not args.json:
        print("--output 必须配合 --json 使用。", file=sys.stderr)
        return 2
    try:
        output_paths = resolve_output_paths(args)
        customer_csv_path = resolve_project_path(args.customer_csv)
        orders_csv_path = resolve_project_path(args.orders_csv)
        artifacts = run_audit(customer_csv_path, orders_csv_path)
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.apply_import:
        source_batch_id = args.source_batch_id or default_source_batch_id()
        import_artifacts = __import__("asyncio").run(
            run_import(
                db_path_value=args.db_path,
                tenant_id=args.tenant_id,
                source_batch_id=source_batch_id,
                customer_csv_path=customer_csv_path,
                orders_csv_path=orders_csv_path,
            )
        )
        import_output_path = output_paths["import_output"]
        import_json_bytes = (
            json.dumps(
                build_import_json_report(
                    import_artifacts,
                    db_path_value=str(resolve_project_path(args.db_path))
                    if args.db_path != ":memory:"
                    else ":memory:",
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
        if import_output_path is None:
            sys.stdout.buffer.write(import_json_bytes)
        else:
            write_json_report(import_output_path, import_json_bytes)
        return 0

    if args.json:
        json_bytes = (
            json.dumps(
                build_json_report(artifacts, customer_csv_path, orders_csv_path),
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
        output_path = output_paths["output"]
        if output_path is None:
            sys.stdout.buffer.write(json_bytes)
        else:
            write_json_report(output_path, json_bytes)
    else:
        print_report(artifacts)

    if output_paths["metrics_output"] is not None:
        write_csv_report(
            output_paths["metrics_output"],
            METRIC_FIELDNAMES,
            [row.to_dict() for row in artifacts.metrics],
        )
    if output_paths["issues_output"] is not None:
        write_csv_report(
            output_paths["issues_output"],
            ISSUE_FIELDNAMES,
            [row.to_dict() for row in artifacts.issues],
        )
    if output_paths["buckets_output"] is not None:
        write_csv_report(
            output_paths["buckets_output"],
            BUCKET_FIELDNAMES,
            [row.to_dict() for row in artifacts.buckets],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
