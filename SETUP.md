# Inventory Backend — Setup & Training Guide

## Prerequisites

- Python 3.12
- PostgreSQL running on `localhost:5432`
- NVIDIA GPU with CUDA 12.1 (for training)
- Git

---

## 1. Clone the Repository

```bash
git clone <your-repo-url>
cd inventory-backend
```

---

## 2. Create & Activate Virtual Environment

```bash
py -3.12 -m venv venv
venv\Scripts\activate
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

> If `loguru` is missing (not in requirements.txt), install it manually:
> ```bash
> pip install loguru
> ```

### Install PyTorch with CUDA 12.1 (GPU support)

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

---

## 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=inventory
DB_USER=postgres
DB_PASSWORD=your_password_here
```

---

## 5. Set Up the Database

Make sure PostgreSQL is running and the `inventory` database exists.

```bash
# Create the database (run once in psql or pgAdmin)
# CREATE DATABASE inventory;

# Then seed the tables
cd db
python seed.py
cd ..
```

---

## 6. Verify Setup

```bash
# Check GPU / CUDA
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"

# Check YOLO model loads
python -c "from ultralytics import YOLO; model = YOLO('yolo26s.pt'); print('YOLO OK')"

# Check database connection
python -c "import psycopg2; conn = psycopg2.connect(host='localhost', port=5432, database='inventory', user='postgres', password='your_password_here'); print('DB OK')"
```

---

## 7. Run the Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Visit the interactive API docs at: `http://localhost:8000/docs`

---

## Training Steps

### Step 1 — Prepare Your Dataset

Place your YOLO-format dataset under:

```
dataset/
  egg.v1i.yolo26/
    train/
      images/
      labels/
```

Update the `base` path in [prepare_dataset.py](prepare_dataset.py) to match your local path, then run:

```bash
python prepare_dataset.py
```

This splits training images 80/20 into `train/` and `valid/` folders and prints a summary.

### Step 2 — Update `train.py` Paths

Open [train.py](train.py) and set the `data` path to your `data.yaml` file:

```python
data='your/path/to/dataset/combined/data.yaml',
```

Your `data.yaml` should look like:

```yaml
path: your/path/to/dataset/combined
train: train/images
val: valid/images

nc: 1
names: ['egg']
```

### Step 3 — Train the Model

```bash
python train.py
```

Training config used:
| Parameter | Value |
|-----------|-------|
| Model     | yolo26s.pt |
| Epochs    | 40 |
| Image size | 640 |
| Batch size | 24 |
| Device    | GPU 0 |
| Workers   | 4 |

Results are saved to `runs/detect/combined_model/`.

### Step 4 — Use the Trained Model

After training, copy the best weights:

```
runs/detect/combined_model/weights/best.pt  →  models/egg/best.pt
```

The scan route will automatically use `models/egg/best.pt` for inference.
