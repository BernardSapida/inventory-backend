import base64
import os
import re
import tempfile
from datetime import date, timedelta
from loguru import logger

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ultralytics import YOLO

from db.connection import get_connection

router = APIRouter()

_model = YOLO('models/combined/best.pt')
logger.info(f"📦 Model path: {_model.ckpt_path}")
logger.info(f"🏷️ Model classes: {_model.names}")

def normalize_name(class_name: str) -> str:
    # egg19 → egg, egg21s → egg
    name = re.sub(r'[^a-zA-Z]', '', class_name)
    return name.lower().strip()

class ScanRequest(BaseModel):
    image: str  # base64 encoded


@router.post("/scan")
def scan_image(request: ScanRequest):
    logger.info("📷 Scan request received!")
    logger.info("🤖 Running YOLO26s inference...")

    # Decode base64
    try:
        image_data = base64.b64decode(request.image)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    # Run YOLO inference — collect boxes grouped by normalized class name
    tmp_path = None
    # maps cls_name → list of box dicts
    class_boxes: dict[str, list[dict]] = {}

    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_data)
            tmp_path = tmp.name

        results = _model(tmp_path, .5)

        for result in results:
            boxes_xyxy = result.boxes.xyxy.tolist()
            confidences = result.boxes.conf.tolist()
            cls_ids = result.boxes.cls.tolist()

            for cls_id, conf, xyxy in zip(cls_ids, confidences, boxes_xyxy):
                raw_name = _model.names[int(cls_id)].lower()
                cls_name = normalize_name(raw_name)
                logger.info(f"🔍 Detected: {raw_name} → normalized: {cls_name} (conf={conf:.2f})")

                box = {
                    "x1": round(xyxy[0]),
                    "y1": round(xyxy[1]),
                    "x2": round(xyxy[2]),
                    "y2": round(xyxy[3]),
                    "confidence": round(conf, 4),
                }
                class_boxes.setdefault(cls_name, []).append(box)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    # Query shelf life from DB and build response
    conn = get_connection()
    cur = conn.cursor()
    detections = []
    today = date.today()

    try:
        for cls_name, boxes in class_boxes.items():
            cur.execute(
                "SELECT shelf_life_days FROM shelf_life_reference WHERE name = %s",
                (cls_name,),
            )
            row = cur.fetchone()
            shelf_life_days = row[0] if row else None
            expiry_date = (today + timedelta(days=shelf_life_days)) if shelf_life_days else None
            quantity = len(boxes)

            logger.info(f"📦 Item: {cls_name} | Qty: {quantity} | Shelf Life: {shelf_life_days} days")

            detections.append({
                "name": cls_name,
                "quantity": quantity,
                "shelf_life_days": shelf_life_days,
                "date_received": str(today),
                "expiry_date": str(expiry_date) if expiry_date else None,
                "boxes": boxes,
            })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

    total_items = sum(d["quantity"] for d in detections)
    logger.success(f"✅ Scan completed! Detected {total_items} item(s) across {len(detections)} class(es)")
    return {"detections": detections, "total_items": total_items}