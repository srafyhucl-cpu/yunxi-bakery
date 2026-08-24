"""客户主档域数据访问层。"""

from app.repository.base import BaseRepository
from app.repository.customer_master_queries import CustomerMasterQueryMixin
from app.repository.customer_master_writes import CustomerMasterWriteMixin


class CustomerMasterRepo(
    CustomerMasterQueryMixin,
    CustomerMasterWriteMixin,
    BaseRepository,
):
    """客户主档与身份链接仓库。"""
