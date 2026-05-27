from fastapi.testclient import TestClient
from api.main import app
import io
import time
from PIL import Image
import numpy as np

def test_fastapi_endpoints():
    print("--- Starting FastAPI Validation ---")
    client = TestClient(app)
    
    print("\n1. Testing Health Endpoint...")
    r = client.get("/api/v1/health/")
    assert r.status_code == 200
    print(f"Health Response: {r.json()}")
    
    print("\n2. Generating Synthetic Upload Dataset (bypassing duplicate filters)...")
    images = []
    for i in range(6):
        img_array = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
        img = Image.fromarray(img_array)
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_byte_arr.seek(0)
        # Using a distinct tuple structure for requests file uploads
        images.append(("files", (f"img_{i}.jpg", img_byte_arr.read(), "image/jpeg")))

    print("\n3. Testing Blocking Upload Ingestion...")
    r = client.post("/api/v1/upload/", files=images)
    print(f"Upload Status: {r.status_code}")
    assert r.status_code == 200
    
    session_data = r.json()
    print(f"Upload Response: {session_data}")
    session_id = session_data["session_id"]
    
    print("\n4. Testing Job Trigger...")
    r = client.post(f"/api/v1/jobs/{session_id}/start", json={"epochs": 1, "video_frames": 1})
    print(f"Start Job Response: {r.json()}")
    assert r.status_code == 200
    
    print("\n5. Testing Job Status Polling & Output Metadata...")
    r = client.get(f"/api/v1/jobs/{session_id}/status")
    print(f"Job Status Response: {r.json()}")
    assert r.status_code == 200
    
    print("\n6. Testing Job Cancellation...")
    r = client.post(f"/api/v1/jobs/{session_id}/cancel")
    print(f"Cancel Job Response: {r.json()}")
    assert r.status_code == 200
    
    # Wait for worker to register cancellation (poll until state changes from TRAINING/QUEUED)
    print("\nWaiting for background cancellation to resolve...")
    max_retries = 15
    for i in range(max_retries):
        r = client.get(f"/api/v1/jobs/{session_id}/status")
        status_data = r.json()
        if status_data["state"] in ["CANCELLED", "COMPLETED", "FAILED"]:
            break
        time.sleep(1.0)
        
    print(f"Job Status After Cancellation Loop: {status_data}")
    assert status_data["state"] == "CANCELLED"
    
    print("\n7. Testing Session Listing...")
    r = client.get("/api/v1/sessions/")
    print(f"Sessions Listing: {r.json()}")
    assert r.status_code == 200
    
    print("\n8. Testing Protected Session Deletion...")
    r = client.delete(f"/api/v1/sessions/{session_id}")
    print(f"Session Delete Response: {r.json()}")
    assert r.status_code == 200
    
    print("\n--- FastAPI Validation Completed Successfully ---")

if __name__ == "__main__":
    test_fastapi_endpoints()
