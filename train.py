from ultralytics import YOLO

if __name__ == '__main__':
    model = YOLO('yolo26s.pt')

    model.train(
        data='F:/Bernard/projects/inventory-backend/dataset/combined/data.yaml',
        epochs=40,
        imgsz=640,
        batch=24,
        device=0,
        workers=4,
        name='combined_model'
    )