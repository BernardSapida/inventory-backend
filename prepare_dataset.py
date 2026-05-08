import os
import shutil
import random

base = 'F:/Bernard/projects/inventory-backend/dataset/egg.v1i.yolo26'

# Get all images
train_images = os.listdir(f'{base}/train/images')
random.shuffle(train_images)

# Split 80% train, 20% valid
split = int(len(train_images) * 0.8)
valid_images = train_images[split:]

# Create valid folders
os.makedirs(f'{base}/valid/images', exist_ok=True)
os.makedirs(f'{base}/valid/labels', exist_ok=True)

# Copy 20% to valid
for img in valid_images:
    shutil.copy(
        f'{base}/train/images/{img}',
        f'{base}/valid/images/{img}'
    )
    label = img.replace('.jpg', '.txt').replace('.png', '.txt')
    label_src = f'{base}/train/labels/{label}'
    if os.path.exists(label_src):
        shutil.copy(label_src, f'{base}/valid/labels/{label}')

print(f"✅ Train: {split} images")
print(f"✅ Valid: {len(valid_images)} images")