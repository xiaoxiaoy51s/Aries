"""桌面宠物资源 API：读取 ~/.codex/pets/ 下的 Codex 宠物（spritesheet.webp + pet.json）。

Codex 宠物规格（参考 hatch-pet 官方 skill）：
    spritesheet.webp: 1536x1872 px，8 列 x 9 行，每帧 192x208 px
    9 行对应的 9 个动画状态及前 N 帧：
        row 0 idle           6 frames
        row 1 running-right  8 frames
        row 2 running-left   8 frames
        row 3 waving         4 frames
        row 4 jumping        5 frames
        row 5 failed         6 frames
        row 6 waiting        6 frames
        row 7 running        8 frames
        row 8 review         6 frames
"""
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel
import json

router = APIRouter(prefix="/pets", tags=["pets"])

CODEX_PETS_DIR = Path.home() / ".Aries" / "pets"

FRAME_WIDTH = 192
FRAME_HEIGHT = 208
COLUMNS = 8
ROWS = 9

# 状态 → (row, frames)，与 Codex hatch-pet 官方约定保持一致
STATES = [
    ("idle", 0, 6),
    ("running-right", 1, 8),
    ("running-left", 2, 8),
    ("waving", 3, 4),
    ("jumping", 4, 5),
    ("failed", 5, 6),
    ("waiting", 6, 6),
    ("running", 7, 8),
    ("review", 8, 6),
]
PREVIEW_STATE = "idle"


class PetState(BaseModel):
    name: str
    row: int
    frames: int


class PetInfo(BaseModel):
    id: str
    name: str
    displayName: str
    description: str
    spritesheetUrl: str
    previewUrl: str
    frameWidth: int
    frameHeight: int
    columns: int
    rows: int
    states: List[PetState]
    # 兼容旧版前端：state-name → spritesheet 同一 URL（解析交给前端）
    animations: dict[str, str]


class PetListResponse(BaseModel):
    pets: List[PetInfo]
    total: int


def _load_manifest(pet_dir: Path) -> Optional[dict]:
    manifest = pet_dir / "pet.json"
    if not manifest.exists():
        return None
    try:
        return json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return None


@router.get("/list", response_model=PetListResponse)
def list_pets() -> PetListResponse:
    """列出 ~/.codex/pets 下所有可用 Codex 宠物。"""
    pets: List[PetInfo] = []
    if not CODEX_PETS_DIR.exists():
        return PetListResponse(pets=pets, total=0)

    states = [PetState(name=n, row=r, frames=f) for n, r, f in STATES]

    for pet_dir in sorted(CODEX_PETS_DIR.iterdir()):
        if not pet_dir.is_dir() or pet_dir.name.startswith("."):
            continue
        manifest = _load_manifest(pet_dir)
        if not manifest:
            continue
        sprite_rel = manifest.get("spritesheetPath", "spritesheet.webp")
        sprite_file = pet_dir / sprite_rel
        if not sprite_file.exists():
            # 兼容 PNG
            alt = pet_dir / "spritesheet.png"
            if alt.exists():
                sprite_file = alt
                sprite_rel = "spritesheet.png"
            else:
                continue

        sprite_url = f"/pets/static/{pet_dir.name}/{sprite_rel}"
        pet_id = manifest.get("id") or pet_dir.name
        display_name = manifest.get("displayName") or pet_dir.name
        description = manifest.get("description") or ""

        animations = {s.name: sprite_url for s in states}

        pets.append(
            PetInfo(
                id=pet_id,
                name=pet_dir.name,
                displayName=display_name,
                description=description,
                spritesheetUrl=sprite_url,
                previewUrl=sprite_url,  # 静态预览也用同图，前端按 idle 行裁剪
                frameWidth=FRAME_WIDTH,
                frameHeight=FRAME_HEIGHT,
                columns=COLUMNS,
                rows=ROWS,
                states=states,
                animations=animations,
            )
        )

    return PetListResponse(pets=pets, total=len(pets))
