"""冷藏箱温控巡检接口：按箱号登记温控要求，录入温度记录并给出超温判定与预警。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.reefer import ReeferService

router = APIRouter(prefix="/api/reefer", tags=["冷藏箱温控巡检"])

service = ReeferService()

LIST_FIELDS = ["箱号", "设定温度", "温度区间", "巡检频次", "温度记录数", "超温记录数", "超温时长（分钟）", "预警", "巡检状态"]
STATUSES = ["待巡检", "巡检中", "已办结"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按箱号检索"),
    status: str | None = Query(default=None, description="待巡检、巡检中、已办结"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按箱号与状态过滤冷藏箱巡检列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出冷藏箱温控巡检清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "reefer", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条冷藏箱巡检明细，含逐条温度记录与判定；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"冷藏箱巡检 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条冷藏箱温控要求；箱温缺失、区间填反等问题先拦下并说明原因。"""
    entry, problems = service.create_entry(payload.values)
    if problems:
        return ActionResult(ok=False, message="；".join(problems))
    return ActionResult(ok=True, message="冷藏箱温控要求已登记", entry=entry)


@router.post("/{entry_id}/records", response_model=ActionResult)
def add_records(entry_id: int, payload: EntryPayload) -> ActionResult:
    """批量录入温度记录：整批校验通过才保存，同一时段重复只留一条。"""
    entry, message = service.add_records(entry_id, payload.values.get("records"))
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条冷藏箱巡检执行开始巡检、结束巡检；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
