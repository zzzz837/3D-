"""CellBasket3D — 管理 Cell ID 的落地/未落地状态"""

from typing import List, Optional, Set

from .exceptions import CellBasketError


class CellBasket3D:
    """与 2D 版 CellBasket 功能等价，管理 3D Cell 的 ID 池。

    规则：
    - 初始状态下所有 ID 均在未落地集合
    - 每次拖出/放置取未落地集合中最小值
    - Cell 删除时 ID 归还到未落地集合
    """

    def __init__(self, total_points: int = 200):
        if not 1 <= total_points <= 200:
            raise ValueError(f"total_points must be 1-200, got {total_points}")
        self._total: int = total_points
        self._unlanded: Set[int] = set(range(total_points))
        self._landed: Set[int] = set()

    @property
    def total_points(self) -> int:
        return self._total

    @property
    def unlanded_count(self) -> int:
        return len(self._unlanded)

    @property
    def landed_count(self) -> int:
        return len(self._landed)

    @property
    def next_id(self) -> Optional[int]:
        """未落地集合中最小 ID。"""
        return min(self._unlanded) if self._unlanded else None

    @property
    def landed_ids(self) -> List[int]:
        return sorted(self._landed)

    @property
    def unlanded_ids(self) -> List[int]:
        return sorted(self._unlanded)

    def land(self, cell_id: int) -> None:
        """标记 cell_id 为已落地。"""
        if cell_id not in self._unlanded:
            raise CellBasketError(f"Cell #{cell_id} not in unlanded set")
        self._unlanded.discard(cell_id)
        self._landed.add(cell_id)

    def unland(self, cell_id: int) -> None:
        """将 cell_id 归还到未落地集合。"""
        if cell_id not in self._landed:
            raise CellBasketError(f"Cell #{cell_id} not in landed set")
        self._landed.discard(cell_id)
        self._unlanded.add(cell_id)

    def is_landed(self, cell_id: int) -> bool:
        return cell_id in self._landed

    def is_unlanded(self, cell_id: int) -> bool:
        return cell_id in self._unlanded

    def resize(self, new_total: int) -> None:
        """调整总通道数（保留已落地 ID，扩展/截断未落地集合）。"""
        if not 1 <= new_total <= 200:
            raise ValueError(f"total_points must be 1-200, got {new_total}")
        if new_total == self._total:
            return
        self._total = new_total
        for i in range(new_total):
            if i not in self._landed:
                self._unlanded.add(i)
        self._unlanded = {i for i in self._unlanded if i < new_total}

    def __repr__(self) -> str:
        return f"CellBasket3D(total={self._total}, landed={self.landed_count}, unlanded={self.unlanded_count})"
