import os
import sys
import uuid
import shutil
import io
import asyncio
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import numpy as np
from PIL import Image
import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import memory manager from memory_engine.py
from memory_engine import mem_manager

# Register a font that supports Vietnamese
try:
    # Use Windows system font Arial
    pdfmetrics.registerFont(TTFont('Arial', 'C:\\Windows\\Fonts\\arial.ttf'))
    DEFAULT_FONT = 'Arial'
except:
    DEFAULT_FONT = 'Helvetica'

# Add current directory and vietocr to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
sys.path.append(os.path.join(current_dir, "vietocr"))

from module.ocr import OCR

app = FastAPI()

# Temporary directories
UPLOAD_DIR = "uploads"
RESULT_DIR = "results"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

# Initialize OCR
ocr_engine = OCR()

# In-memory task status
tasks = {}

class ChatRequest(BaseModel):
    message: str
    user_id: str = "researcher_01"

def process_pdf_task(task_id: str, input_path: str, output_path: str, txt_path: str):
    try:
        tasks[task_id] = {"status": "processing", "progress": 0}
        all_text = []
        
        # 1. PDF to Images
        with pdfplumber.open(input_path) as pdf:
            total_pages = len(pdf.pages)
            c = canvas.Canvas(output_path)
            
            for i, page in enumerate(pdf.pages):
                # Update progress
                tasks[task_id]["progress"] = int((i / total_pages) * 100)
                
                # Convert page to image
                img = page.to_image(resolution=150).original
                img_width, img_height = img.size
                
                # Run OCR
                # OCR returns list of (bbox, text_result) where text_result is (text, score)
                ocr_results = ocr_engine(np.array(img))
                
                # Generate PDF page
                c.setPageSize((img_width, img_height))
                
                # Draw the original image as background
                # Save temp image for reportlab
                temp_img_path = f"tmp_{task_id}_{i}.jpg"
                img.save(temp_img_path)
                c.drawImage(temp_img_path, 0, 0, width=img_width, height=img_height)
                
                # Overlay OCR text
                # We make the text invisible but selectable if we want, 
                # but for now let's make it visible or semi-transparent for debugging/demo
                # To make it "searchable PDF", we use a transparent color
                c.setFillColorRGB(0, 0, 0, alpha=0) 
                
                for box, (text, score) in ocr_results:
                    if not text: continue
                    
                    # box format from ocr.py: [ [x1,y1], [x2,y2], [x3,y3], [x4,y4] ]
                    # ReportLab uses coordinates from bottom-left
                    x_coords = [p[0] for p in box]
                    y_coords = [p[1] for p in box]
                    
                    x_min, x_max = min(x_coords), max(x_coords)
                    y_min, y_max = min(y_coords), max(y_coords)
                    
                    text_w = x_max - x_min
                    text_h = y_max - y_min
                    
                    # Convert top-left based coordinates to bottom-left based
                    rl_x = x_min
                    rl_y = img_height - y_max
                    
                    # Estimate font size based on box height
                    font_size = max(1, int(text_h * 0.8))
                    c.setFont(DEFAULT_FONT, font_size) 
                    
                    # Draw text
                    c.drawString(rl_x, rl_y + (text_h * 0.2), text)
                    all_text.append(text)
                
                c.showPage()
                os.remove(temp_img_path)
            
            c.save()
            
            # Save all text to txt file
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(all_text))
            
        tasks[task_id] = {"status": "completed", "progress": 100, "result_url": f"/download/{task_id}", "txt_url": f"/download_txt/{task_id}"}
    except Exception as e:
        tasks[task_id] = {"status": "failed", "error": str(e)}
        print(f"Error processing task {task_id}: {e}")

@app.post("/upload")
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    task_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{task_id}.pdf")
    output_path = os.path.join(RESULT_DIR, f"{task_id}_searchable.pdf")
    txt_path = os.path.join(RESULT_DIR, f"{task_id}.txt")
    
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    tasks[task_id] = {"status": "pending", "progress": 0}
    background_tasks.add_task(process_pdf_task, task_id, input_path, output_path, txt_path)
    
    return {"task_id": task_id}

@app.get("/status/{task_id}")
async def get_status(task_id: str):
    if task_id not in tasks:
        return JSONResponse(status_code=404, content={"message": "Task not found"})
    return tasks[task_id]

@app.get("/download/{task_id}")
async def download_result(task_id: str):
    output_path = os.path.join(RESULT_DIR, f"{task_id}_searchable.pdf")
    if os.path.exists(output_path):
        return FileResponse(output_path, media_type="application/pdf", filename="ocr_result.pdf")
    return JSONResponse(status_code=404, content={"message": "Result not ready or not found"})

@app.get("/download_txt/{task_id}")
async def download_txt(task_id: str):
    txt_path = os.path.join(RESULT_DIR, f"{task_id}.txt")
    if os.path.exists(txt_path):
        return FileResponse(txt_path, media_type="text/plain", filename="ocr_result.txt")
    return JSONResponse(status_code=404, content={"message": "Result not ready or not found"})

# Serve static files
app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.post("/chat")
async def chat(request: ChatRequest):
    user_input = request.message
    
    # Bước 1: Truy xuất ký ức liên quan
    try:
        context = mem_manager.get_context(user_input)
    except Exception as e:
        print(f"Memory retrieval error: {e}")
        context = ""

    # Bước 2: Truyền context vào Prompt và gửi cho AI
    # Sử dụng System Prompt tùy chỉnh từ người dùng
    system_instruction = f"""
## SYSTEM INSTRUCTION
Bạn là một trợ lý nghiên cứu và phát triển phần mềm (Python/Flet expert).

## LONG-TERM CONTEXT (Từ Mem0):
<memory>
{context}
</memory>

## QUY TẮC:
1. Sử dụng thông tin trong <memory> để hiểu về dự án hiện tại (Photobooth, Luận văn Quản lý công, v.v.) mà không cần nhắc lại câu hỏi cũ.
2. Nếu thông tin trong <memory> đã cũ, hãy ưu tiên thông tin mới nhất từ người dùng.
3. Phản hồi súc tích, tập trung vào giải pháp kỹ thuật và kiến trúc Material Design 3.
"""
    
    prompt = f"{system_instruction}\nNgười dùng hỏi: {user_input}\nPhản hồi:"

    try:
        # Sử dụng Gemini (có thể thay bằng OpenAI nếu người dùng cung cấp key)
        import google.generativeai as genai
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return JSONResponse(status_code=500, content={"message": "Thiếu API Key (GEMINI_API_KEY). Vui lòng thêm vào file .env"})
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        response = model.generate_content(prompt)
        ai_response = response.text

        # Bước 3: Lưu lại thông tin quan trọng sau cuộc hội thoại
        try:
            mem_manager.save_insight(user_input, ai_response)
        except Exception as e:
            print(f"Memory storage error: {e}")
        
        return {"response": ai_response}
    except Exception as e:
        print(f"Chat error: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
