"""
数据库表结构定义。

所有 CREATE TABLE / CREATE INDEX 语句集中管理于此。
连接管理与迁移执行器在 app/database.py 中。
"""

SCHEMA_STATEMENTS: list[str] = [
    # 会话表
    """CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        channel TEXT NOT NULL,
        user_id TEXT NOT NULL,
        staff_id TEXT DEFAULT '',
        status TEXT DEFAULT 'active'
            CHECK(status IN ('active','transfer_pending','human_service','closed')),
        extra_info TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)",
    # 消息表
    """CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id),
        role TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')),
        content TEXT NOT NULL DEFAULT '',
        channel_msg_id TEXT DEFAULT '',
        estimated_tokens INTEGER DEFAULT 0,
        tool_calls TEXT DEFAULT '[]',
        tool_name TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_messages_ymid ON messages(channel_msg_id)",
    # 知识库表
    """CREATE TABLE IF NOT EXISTS knowledge_base (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL
            CHECK(category IN ('store_info','product','policy','faq','after_sales')),
        content_type TEXT NOT NULL DEFAULT 'faq',
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        keywords TEXT DEFAULT '',
        priority INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        last_sync_source TEXT DEFAULT 'admin_manual',
        last_sync_ref TEXT DEFAULT '',
        content_origin TEXT DEFAULT 'admin_manual',
        created_by TEXT DEFAULT '',
        updated_by TEXT DEFAULT '',
        suggested_category TEXT DEFAULT '',
        suggest_reason TEXT DEFAULT '',
        vector_sync_status TEXT DEFAULT 'pending',
        vector_synced_at TEXT DEFAULT '',
        vector_sync_error TEXT DEFAULT '',
        vector_sync_retry_count INTEGER DEFAULT 0,
        audience TEXT DEFAULT 'all',
        review_status TEXT DEFAULT 'published',
        valid_from TEXT DEFAULT '',
        valid_until TEXT DEFAULT '',
        reviewed_by TEXT DEFAULT '',
        reviewed_at TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_kb_category ON knowledge_base(category)",
    "CREATE INDEX IF NOT EXISTS idx_kb_governance_lookup ON knowledge_base(is_active, review_status, audience, valid_from, valid_until)",
    # 知识检索命中日志：用于客户/员工知识命中观测
    """CREATE TABLE IF NOT EXISTS knowledge_retrieval_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_type TEXT NOT NULL DEFAULT '',
        audience TEXT NOT NULL DEFAULT 'all',
        query TEXT NOT NULL DEFAULT '',
        query_hash TEXT NOT NULL DEFAULT '',
        query_category TEXT NOT NULL DEFAULT '',
        retrieval_mode TEXT NOT NULL DEFAULT '',
        matched_entry_ids_json TEXT NOT NULL DEFAULT '[]',
        matched_titles_json TEXT NOT NULL DEFAULT '[]',
        result_count INTEGER NOT NULL DEFAULT 0,
        fallback_reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_krl_created_at ON knowledge_retrieval_logs(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_krl_bot_audience_created ON knowledge_retrieval_logs(bot_type, audience, created_at)",
    # 人工转接表
    """CREATE TABLE IF NOT EXISTS human_transfers (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id),
        user_id TEXT NOT NULL,
        staff_id TEXT DEFAULT '',
        reason TEXT DEFAULT '',
        status TEXT DEFAULT 'pending'
            CHECK(status IN ('pending','accepted','rejected','closed')),
        conversation_summary TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        accepted_at TEXT,
        closed_at TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_transfers_session ON human_transfers(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_transfers_status ON human_transfers(status)",
    # 订单表
    """CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id),
        channel TEXT NOT NULL,
        user_id TEXT NOT NULL,
        products TEXT NOT NULL,
        total_amount REAL DEFAULT 0,
        delivery TEXT DEFAULT '{}',
        payment TEXT DEFAULT '{}',
        status TEXT DEFAULT 'pending'
            CHECK(status IN ('pending','confirmed','making','delivering','done','cancelled')),
        remark TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)",
    """CREATE TABLE IF NOT EXISTS payment_transactions (
        transaction_id TEXT PRIMARY KEY,
        order_id TEXT NOT NULL UNIQUE REFERENCES orders(id),
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_payment_transactions_order ON payment_transactions(order_id)",
    # 小程序订单状态事件表
    """CREATE TABLE IF NOT EXISTS order_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT NOT NULL,
        status TEXT NOT NULL,
        operator TEXT NOT NULL DEFAULT 'system',
        note TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_order_events_order ON order_events(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_events_created ON order_events(created_at)",
    # 小程序收货地址表
    """CREATE TABLE IF NOT EXISTS miniapp_addresses (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        receiver_name TEXT NOT NULL,
        receiver_phone TEXT NOT NULL,
        address TEXT NOT NULL,
        is_default INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_miniapp_addresses_user ON miniapp_addresses(user_id)",
    # 小程序地址操作审计表
    """CREATE TABLE IF NOT EXISTS miniapp_address_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        address_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        operator TEXT NOT NULL DEFAULT 'admin',
        action TEXT NOT NULL,
        before_json TEXT DEFAULT '{}',
        after_json TEXT DEFAULT '{}',
        note TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_miniapp_address_audit_address ON miniapp_address_audit(address_id)",
    "CREATE INDEX IF NOT EXISTS idx_miniapp_address_audit_user ON miniapp_address_audit(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_miniapp_address_audit_created ON miniapp_address_audit(created_at)",
    # 店铺配置表
    """CREATE TABLE IF NOT EXISTS shop_config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    # 有赞商品与实时库存大宽表
    """CREATE TABLE IF NOT EXISTS youzan_products (
        item_id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        alias TEXT NOT NULL UNIQUE,
        price_fen INTEGER NOT NULL,
        stock INTEGER NOT NULL,
        image TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        skus_json TEXT DEFAULT '[]',
        item_props_json TEXT DEFAULT '[]',
        desc TEXT DEFAULT '',
        tags TEXT DEFAULT '',
        tag_ids_json TEXT DEFAULT '[]',
        classification_ids_json TEXT DEFAULT '[]',
        group_ids_json TEXT DEFAULT '[]',
        second_group_ids_json TEXT DEFAULT '[]',
        leaf_category_ids_json TEXT DEFAULT '[]',
        item_no TEXT DEFAULT '',
        last_sync_source TEXT DEFAULT 'product_reconcile',
        last_sync_ref TEXT DEFAULT '',
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_yp_title ON youzan_products(title)",
    "CREATE INDEX IF NOT EXISTS idx_yp_alias ON youzan_products(alias)",
    "CREATE INDEX IF NOT EXISTS idx_yp_tag_ids ON youzan_products(tag_ids_json)",
    "CREATE INDEX IF NOT EXISTS idx_yp_classification_ids ON youzan_products(classification_ids_json)",
    "CREATE INDEX IF NOT EXISTS idx_yp_group_ids ON youzan_products(group_ids_json)",
    "CREATE INDEX IF NOT EXISTS idx_yp_second_group_ids ON youzan_products(second_group_ids_json)",
    "CREATE INDEX IF NOT EXISTS idx_yp_leaf_category_ids ON youzan_products(leaf_category_ids_json)",
    # 有赞商品分组映射表
    """CREATE TABLE IF NOT EXISTS youzan_product_categories (
        tag_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        sort INTEGER DEFAULT 0,
        product_count INTEGER DEFAULT 0,
        is_public INTEGER DEFAULT 1,
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ypc_sort ON youzan_product_categories(sort, title)",
    # 有赞交易订单大宽表
    """CREATE TABLE IF NOT EXISTS youzan_orders (
        order_no TEXT PRIMARY KEY,
        buyer_id TEXT NOT NULL,
        status TEXT NOT NULL,
        amount_fen INTEGER NOT NULL,
        logistics_no TEXT DEFAULT '',
        logistics_status TEXT DEFAULT '',
        product_titles TEXT NOT NULL,
        total_quantity INTEGER NOT NULL,
        pay_time TEXT DEFAULT '',
        consign_time TEXT DEFAULT '',
        pay_type_str TEXT DEFAULT '',
        express_type INTEGER DEFAULT 0,
        refund_state INTEGER DEFAULT 0,
        post_fee_fen INTEGER DEFAULT 0,
        discount_fen INTEGER DEFAULT 0,
        delivery_province TEXT DEFAULT '',
        delivery_city TEXT DEFAULT '',
        delivery_district TEXT DEFAULT '',
        delivery_time TEXT DEFAULT '',
        outer_user_id TEXT DEFAULT '',
        order_items_json TEXT DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_yo_status ON youzan_orders(status)",
    "CREATE INDEX IF NOT EXISTS idx_yo_buyer ON youzan_orders(buyer_id)",
    # analytics_events（分析埋点日志物理大宽表）
    """CREATE TABLE IF NOT EXISTS analytics_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        buyer_id TEXT,
        event_type TEXT NOT NULL,
        event_source TEXT NOT NULL,
        ref_id TEXT,
        meta_data TEXT DEFAULT '{}',
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ae_type ON analytics_events(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_ae_session ON analytics_events(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_ae_buyer ON analytics_events(buyer_id)",
    "CREATE INDEX IF NOT EXISTS idx_ae_created ON analytics_events(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_events_attribution_flow ON analytics_events(buyer_id, event_type, created_at)",
    # 有赞 Webhook 审计表
    """CREATE TABLE IF NOT EXISTS youzan_webhook_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_id TEXT NOT NULL UNIQUE,
        trace_id TEXT DEFAULT '',
        event_type TEXT DEFAULT '',
        business_type TEXT NOT NULL
            CHECK(business_type IN ('trade','item','chat','unknown')),
        business_key TEXT DEFAULT '',
        status TEXT NOT NULL
            CHECK(status IN ('received','processing','processed','skipped','failed','duplicate')),
        http_status INTEGER DEFAULT 200,
        process_stage TEXT DEFAULT '',
        error_type TEXT DEFAULT '',
        error_message TEXT DEFAULT '',
        payload_hash TEXT DEFAULT '',
        payload_summary_json TEXT DEFAULT '{}',
        received_at TEXT NOT NULL,
        process_started_at TEXT,
        process_finished_at TEXT,
        duration_ms INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ywe_received ON youzan_webhook_events(received_at)",
    "CREATE INDEX IF NOT EXISTS idx_ywe_status ON youzan_webhook_events(status)",
    "CREATE INDEX IF NOT EXISTS idx_ywe_event_type ON youzan_webhook_events(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_ywe_business_key ON youzan_webhook_events(business_key)",
    # content_change_history（内容变更历史）
    """CREATE TABLE IF NOT EXISTS content_change_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL
            CHECK(entity_type IN ('product','knowledge')),
        entity_key TEXT NOT NULL,
        category TEXT DEFAULT '',
        title TEXT DEFAULT '',
        source TEXT NOT NULL,
        source_ref TEXT DEFAULT '',
        session_id TEXT DEFAULT '',
        webhook_msg_id TEXT DEFAULT '',
        action TEXT DEFAULT '',
        status TEXT NOT NULL
            CHECK(status IN ('success','failed')),
        change_summary_json TEXT DEFAULT '{}',
        error_type TEXT DEFAULT '',
        error_message TEXT DEFAULT '',
        occurred_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cch_occurred ON content_change_history(occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_cch_source ON content_change_history(source)",
    "CREATE INDEX IF NOT EXISTS idx_cch_status ON content_change_history(status)",
    "CREATE INDEX IF NOT EXISTS idx_cch_entity ON content_change_history(entity_type, entity_key)",
    # 客户主档：一个逻辑客户一行，只保存稳定主档真相
    """CREATE TABLE IF NOT EXISTS customer_master (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active'
            CHECK(status IN ('active','merged','archived')),
        merge_into_customer_id TEXT REFERENCES customer_master(id),
        primary_phone TEXT DEFAULT '',
        phone_verified INTEGER NOT NULL DEFAULT 0
            CHECK(phone_verified IN (0,1)),
        display_name TEXT DEFAULT '',
        gender TEXT NOT NULL DEFAULT 'unknown'
            CHECK(gender IN ('unknown','male','female','other')),
        birthday TEXT DEFAULT '',
        wechat_region TEXT DEFAULT '',
        first_seen_at TEXT DEFAULT '',
        last_seen_at TEXT DEFAULT '',
        first_source TEXT DEFAULT ''
            CHECK(first_source IN ('','youzan','miniapp','wecom','import','manual')),
        identity_confidence TEXT NOT NULL DEFAULT 'low'
            CHECK(identity_confidence IN ('high','medium','low')),
        has_youzan_identity INTEGER NOT NULL DEFAULT 0
            CHECK(has_youzan_identity IN (0,1)),
        has_miniapp_identity INTEGER NOT NULL DEFAULT 0
            CHECK(has_miniapp_identity IN (0,1)),
        has_wecom_identity INTEGER NOT NULL DEFAULT 0
            CHECK(has_wecom_identity IN (0,1)),
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cm_tenant_status ON customer_master(tenant_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_cm_tenant_phone ON customer_master(tenant_id, primary_phone)",
    "CREATE INDEX IF NOT EXISTS idx_cm_tenant_first_seen ON customer_master(tenant_id, first_seen_at)",
    "CREATE INDEX IF NOT EXISTS idx_cm_tenant_last_seen ON customer_master(tenant_id, last_seen_at)",
    "CREATE INDEX IF NOT EXISTS idx_cm_merge_into ON customer_master(merge_into_customer_id)",
    # 客户身份链接：承接手机号、有赞、小程序、企微等多来源身份
    """CREATE TABLE IF NOT EXISTS customer_identity_links (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        customer_id TEXT NOT NULL REFERENCES customer_master(id),
        identity_type TEXT NOT NULL
            CHECK(identity_type IN ('phone','youzan_customer','miniapp_openid','wecom_external_user','wecom_union','manual')),
        identity_value TEXT NOT NULL,
        identity_value_normalized TEXT,
        source_system TEXT NOT NULL
            CHECK(source_system IN ('youzan','miniapp','wecom','import','manual')),
        source_record_id TEXT DEFAULT '',
        source_label TEXT DEFAULT '',
        link_status TEXT NOT NULL DEFAULT 'active'
            CHECK(link_status IN ('active','pending_review','rejected','merged')),
        verification_status TEXT NOT NULL DEFAULT 'unverified'
            CHECK(verification_status IN ('unverified','inferred','verified','manual_confirmed')),
        confidence_score INTEGER NOT NULL DEFAULT 0
            CHECK(confidence_score >= 0 AND confidence_score <= 100),
        first_seen_at TEXT DEFAULT '',
        last_seen_at TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        UNIQUE(tenant_id, identity_type, identity_value),
        UNIQUE(tenant_id, identity_type, identity_value_normalized)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cil_customer ON customer_identity_links(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_cil_tenant_type_norm ON customer_identity_links(tenant_id, identity_type, identity_value_normalized)",
    "CREATE INDEX IF NOT EXISTS idx_cil_tenant_status ON customer_identity_links(tenant_id, link_status)",
    "CREATE INDEX IF NOT EXISTS idx_cil_source_record ON customer_identity_links(source_system, source_record_id)",
    "CREATE INDEX IF NOT EXISTS idx_cil_seen_at ON customer_identity_links(tenant_id, last_seen_at)",
    # 客户来源快照：保留来源原始真相和标准化真相
    """CREATE TABLE IF NOT EXISTS customer_source_snapshots (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        customer_id TEXT REFERENCES customer_master(id),
        identity_link_id TEXT REFERENCES customer_identity_links(id),
        source_system TEXT NOT NULL
            CHECK(source_system IN ('youzan','miniapp','wecom','import','manual')),
        source_object_type TEXT NOT NULL
            CHECK(source_object_type IN ('customer','order_buyer','member','contact')),
        source_record_id TEXT NOT NULL,
        source_batch_id TEXT NOT NULL,
        snapshot_json TEXT NOT NULL DEFAULT '{}',
        normalized_json TEXT NOT NULL DEFAULT '{}',
        field_hash TEXT NOT NULL DEFAULT '',
        captured_at TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(tenant_id, source_system, source_object_type, source_record_id, source_batch_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_css_customer ON customer_source_snapshots(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_css_identity_link ON customer_source_snapshots(identity_link_id)",
    "CREATE INDEX IF NOT EXISTS idx_css_source_record ON customer_source_snapshots(source_system, source_record_id)",
    "CREATE INDEX IF NOT EXISTS idx_css_batch ON customer_source_snapshots(source_batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_css_captured_at ON customer_source_snapshots(captured_at)",
    "CREATE INDEX IF NOT EXISTS idx_css_field_hash ON customer_source_snapshots(field_hash)",
    # 客户合并复核：承接 pending_review 人工判断闭环
    """CREATE TABLE IF NOT EXISTS customer_merge_reviews (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        review_type TEXT NOT NULL
            CHECK(review_type IN ('identity_conflict','candidate_merge','weak_identity_enrichment')),
        review_status TEXT NOT NULL DEFAULT 'open'
            CHECK(review_status IN ('open','in_progress','approved_merge','rejected_merge','needs_more_evidence')),
        source_customer_id TEXT REFERENCES customer_master(id),
        target_customer_id TEXT REFERENCES customer_master(id),
        primary_identity_link_id TEXT REFERENCES customer_identity_links(id),
        review_reason TEXT NOT NULL DEFAULT '',
        conflict_summary_json TEXT NOT NULL DEFAULT '{}',
        evidence_snapshot_ids_json TEXT NOT NULL DEFAULT '[]',
        decision TEXT DEFAULT ''
            CHECK(decision IN ('','merge','keep_separate','reject_identity','wait')),
        decision_notes TEXT DEFAULT '',
        reviewed_by TEXT DEFAULT '',
        reviewed_at TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cmr_tenant_status ON customer_merge_reviews(tenant_id, review_status)",
    "CREATE INDEX IF NOT EXISTS idx_cmr_source_customer ON customer_merge_reviews(source_customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_cmr_target_customer ON customer_merge_reviews(target_customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_cmr_identity_link ON customer_merge_reviews(primary_identity_link_id)",
    "CREATE INDEX IF NOT EXISTS idx_cmr_reviewed_at ON customer_merge_reviews(reviewed_at)",
    # 顾客长期记忆画像
    """CREATE TABLE IF NOT EXISTS customer_profiles (
        id TEXT PRIMARY KEY,
        channel TEXT NOT NULL,
        user_id TEXT NOT NULL,
        display_name TEXT DEFAULT '',
        preferences_json TEXT DEFAULT '{}',
        order_summary_json TEXT DEFAULT '{}',
        special_dates_json TEXT DEFAULT '[]',
        allergens_json TEXT DEFAULT '[]',
        consent_status TEXT DEFAULT 'unknown'
            CHECK(consent_status IN ('unknown','granted','revoked')),
        source_evidence_json TEXT DEFAULT '{}',
        last_interaction_at TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        UNIQUE(channel, user_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cp_channel_user ON customer_profiles(channel, user_id)",
    # 客户会话短期摘要：只服务当前会话上下文，不直接进入长期画像
    """CREATE TABLE IF NOT EXISTS conversation_summaries (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id),
        channel TEXT NOT NULL,
        user_id TEXT NOT NULL,
        summary_text TEXT NOT NULL,
        state_json TEXT NOT NULL DEFAULT '{}',
        source_message_ids_json TEXT NOT NULL DEFAULT '[]',
        source_until_message_id TEXT DEFAULT '',
        token_estimate INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active'
            CHECK(status IN ('active','superseded','discarded')),
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cs_session_status ON conversation_summaries(session_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_cs_channel_user ON conversation_summaries(channel, user_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_cs_active_session ON conversation_summaries(session_id) WHERE status = 'active'",
    # 企业微信客户群绑定：承接 opengid/chat_id 归因与运营批次
    """CREATE TABLE IF NOT EXISTS customer_groups (
        id TEXT PRIMARY KEY,
        chat_id TEXT NOT NULL UNIQUE,
        opengid TEXT DEFAULT '',
        name TEXT DEFAULT '',
        owner_userid TEXT DEFAULT '',
        source TEXT DEFAULT '',
        status TEXT DEFAULT 'active'
            CHECK(status IN ('active','archived')),
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cg_opengid ON customer_groups(opengid)",
    "CREATE INDEX IF NOT EXISTS idx_cg_owner ON customer_groups(owner_userid)",
    # 客户群团购/预订活动批次
    """CREATE TABLE IF NOT EXISTS group_campaigns (
        id TEXT PRIMARY KEY,
        group_id TEXT NOT NULL REFERENCES customer_groups(id),
        title TEXT NOT NULL,
        status TEXT DEFAULT 'active'
            CHECK(status IN ('active','closed','archived')),
        starts_at TEXT DEFAULT '',
        ends_at TEXT DEFAULT '',
        summary_note TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_gc_group_status ON group_campaigns(group_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_gc_updated ON group_campaigns(updated_at)",
    # 客户群结构化登记：替代原生群接龙，供后台汇总和微信客服查询
    """CREATE TABLE IF NOT EXISTS group_registrations (
        id TEXT PRIMARY KEY,
        campaign_id TEXT NOT NULL REFERENCES group_campaigns(id),
        group_id TEXT NOT NULL REFERENCES customer_groups(id),
        user_id TEXT NOT NULL,
        customer_name TEXT NOT NULL,
        customer_phone TEXT NOT NULL,
        product_name TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
        fulfillment_method TEXT DEFAULT 'pickup'
            CHECK(fulfillment_method IN ('pickup','delivery')),
        desired_time TEXT DEFAULT '',
        address TEXT DEFAULT '',
        remark TEXT DEFAULT '',
        status TEXT DEFAULT 'pending'
            CHECK(status IN ('pending','confirmed','cancelled')),
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_gr_campaign_status ON group_registrations(campaign_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_gr_group ON group_registrations(group_id)",
    "CREATE INDEX IF NOT EXISTS idx_gr_user ON group_registrations(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_gr_phone ON group_registrations(customer_phone)",
    # 离线会话质检结果
    """CREATE TABLE IF NOT EXISTS conversation_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL REFERENCES sessions(id),
        quality_score INTEGER NOT NULL CHECK(quality_score >= 0 AND quality_score <= 100),
        issues_json TEXT DEFAULT '[]',
        reviewer_model TEXT DEFAULT '',
        reviewed_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cr_session ON conversation_reviews(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_cr_score ON conversation_reviews(quality_score)",
    # 知识缺口建议，人工审核后才可进入知识库
    """CREATE TABLE IF NOT EXISTS knowledge_gaps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_norm TEXT NOT NULL,
        frequency INTEGER DEFAULT 1,
        status TEXT DEFAULT 'open'
            CHECK(status IN ('open','proposed','resolved','rejected')),
        proposed_answer TEXT DEFAULT '',
        related_sessions_json TEXT DEFAULT '[]',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_kg_status ON knowledge_gaps(status)",
    "CREATE INDEX IF NOT EXISTS idx_kg_freq ON knowledge_gaps(frequency)",
    # 微信客服同步状态：保存 sync_msg cursor，抵御历史回放
    """CREATE TABLE IF NOT EXISTS wecom_kf_sync_states (
        open_kfid TEXT PRIMARY KEY,
        last_cursor TEXT DEFAULT '',
        status TEXT DEFAULT 'idle'
            CHECK(status IN ('idle','syncing','failed')),
        last_error TEXT DEFAULT '',
        retry_count INTEGER DEFAULT 0,
        last_synced_at TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    # 微信客服消息账本：按 msgid 做持久化幂等
    """CREATE TABLE IF NOT EXISTS wecom_kf_message_ledger (
        msg_id TEXT PRIMARY KEY,
        open_kfid TEXT DEFAULT '',
        external_userid TEXT DEFAULT '',
        origin INTEGER DEFAULT 0,
        msgtype TEXT DEFAULT '',
        event_type TEXT DEFAULT '',
        process_action TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_wkms_open_kfid ON wecom_kf_message_ledger(open_kfid)",
    "CREATE INDEX IF NOT EXISTS idx_wkms_external_user ON wecom_kf_message_ledger(external_userid)",
]

PRAGMA_STATEMENTS: list[str] = [
    "PRAGMA journal_mode = WAL",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA foreign_keys = ON",
    "PRAGMA auto_vacuum = INCREMENTAL",
]
