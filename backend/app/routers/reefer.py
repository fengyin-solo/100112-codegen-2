"""冷藏箱温控巡检接口：按箱号登记箱温与温度记录，超温判定口径收在服务端一条规则里。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.reefer import ReeferService

router = APIRouter(prefix="/api/reefer", tags=["冷藏箱温控"])

service = ReeferService()

STATUSES = ["正常", "预警", "超温"]


@router.get("/summary")
def summary() -> dict[str, int]:
    """温控汇总：在港冷藏箱、超温箱量、预警箱量，与列表、详情同源推导。"""
    return service.summary()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出冷藏箱温控清单：返回当前全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "reefer", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按箱号检索"),
    status: str | None = Query(default=None, description="正常、预警、超温"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按箱号与判定结果过滤冷藏箱列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条冷藏箱明细（含温度记录）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"冷藏箱 {entry_id} 不存在或已离场")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记冷藏箱：箱温缺失、区间填反都会被拦下并说明原因。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/readings", response_model=ActionResult)
def submit_readings(entry_id: int, payload: EntryPayload) -> ActionResult:
    """提交一批巡检温度记录：整批校验通过才落库，同一时段的记录只留一条。"""
    readings = payload.values.get("温度记录") or []
    if not isinstance(readings, list):
        return ActionResult(ok=False, message="温度记录要按列表提交，未保存")
    inspector = str(payload.values.get("巡检人") or "").strip()
    entry, message = service.submit_readings(entry_id, readings, inspector)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
