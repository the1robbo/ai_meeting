from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime
import aiofiles
import asyncio
from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
import tempfile
import shutil

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Create uploads directory
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Define Models
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str

class QuestionAnswer(BaseModel):
    question: str
    answer: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class MeetingRecording(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    audio_file_path: Optional[str] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    key_points: Optional[List[str]] = None
    action_items: Optional[List[str]] = None
    questions_answers: Optional[List[QuestionAnswer]] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    status: str = "recording"  # recording, processing, completed, error

class MeetingCreate(BaseModel):
    title: str

class ProcessingResponse(BaseModel):
    meeting_id: str
    status: str
    message: str

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "AI Meeting Summarizer API"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.dict())
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]

@api_router.post("/meetings", response_model=MeetingRecording)
async def create_meeting(meeting: MeetingCreate):
    """Create a new meeting recording session"""
    meeting_dict = meeting.dict()
    meeting_obj = MeetingRecording(**meeting_dict)
    result = await db.meetings.insert_one(meeting_obj.dict())
    return meeting_obj

@api_router.get("/meetings", response_model=List[MeetingRecording])
async def get_meetings():
    """Get all meeting recordings"""
    meetings = await db.meetings.find().sort("created_at", -1).to_list(100)
    return [MeetingRecording(**meeting) for meeting in meetings]

@api_router.get("/meetings/{meeting_id}", response_model=MeetingRecording)
async def get_meeting(meeting_id: str):
    """Get a specific meeting recording"""
    meeting = await db.meetings.find_one({"id": meeting_id})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return MeetingRecording(**meeting)

@api_router.post("/meetings/{meeting_id}/upload-audio")
async def upload_audio(meeting_id: str, audio_file: UploadFile = File(...)):
    """Upload audio file for a meeting"""
    try:
        # Check if meeting exists
        meeting = await db.meetings.find_one({"id": meeting_id})
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        # Save uploaded file
        file_extension = audio_file.filename.split('.')[-1] if '.' in audio_file.filename else 'wav'
        audio_filename = f"{meeting_id}.{file_extension}"
        audio_path = UPLOAD_DIR / audio_filename
        
        async with aiofiles.open(audio_path, 'wb') as f:
            content = await audio_file.read()
            await f.write(content)
        
        # Update meeting with audio file path
        await db.meetings.update_one(
            {"id": meeting_id},
            {"$set": {"audio_file_path": str(audio_path), "status": "uploaded"}}
        )
        
        return {"message": "Audio uploaded successfully", "meeting_id": meeting_id}
    
    except Exception as e:
        logger.error(f"Error uploading audio: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error uploading audio: {str(e)}")

@api_router.post("/meetings/{meeting_id}/process", response_model=ProcessingResponse)
async def process_meeting(meeting_id: str):
    """Process meeting audio with AI (transcription and summarization)"""
    try:
        # Get meeting
        meeting = await db.meetings.find_one({"id": meeting_id})
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        if not meeting.get("audio_file_path"):
            raise HTTPException(status_code=400, detail="No audio file uploaded")
        
        # Update status to processing
        await db.meetings.update_one(
            {"id": meeting_id},
            {"$set": {"status": "processing"}}
        )
        
        # Process in background (you could use Celery for production)
        asyncio.create_task(process_audio_with_ai(meeting_id, meeting["audio_file_path"]))
        
        return ProcessingResponse(
            meeting_id=meeting_id,
            status="processing",
            message="Meeting processing started. This may take a few minutes."
        )
        
    except Exception as e:
        logger.error(f"Error processing meeting: {str(e)}")
        await db.meetings.update_one(
            {"id": meeting_id},
            {"$set": {"status": "error"}}
        )
        raise HTTPException(status_code=500, detail=f"Error processing meeting: {str(e)}")

async def process_audio_with_ai(meeting_id: str, audio_file_path: str):
    """Background task to process audio with AI"""
    try:
        logger.info(f"Starting AI processing for meeting {meeting_id}")
        
        # For audio transcription, we need to use a different approach since file attachments
        # with Whisper aren't supported in the current emergentintegrations version
        # Let's use OpenAI directly for transcription
        
        # First, let's use Gemini for file processing since it supports file attachments
        transcription_chat = LlmChat(
            api_key=os.environ['EMERGENT_LLM_KEY'],
            session_id=f"transcribe_{meeting_id}",
            system_message="You are a transcription assistant. Listen to the audio and convert it to accurate text. Please transcribe exactly what you hear."
        ).with_model("gemini", "gemini-2.0-flash")
        
        # Create file content for audio transcription
        audio_file = FileContentWithMimeType(
            file_path=audio_file_path,
            mime_type="audio/wav"  # Adjust based on actual file type
        )
        
        # Transcribe audio using Gemini
        logger.info(f"Transcribing audio for meeting {meeting_id}")
        transcription_message = UserMessage(
            text="Please transcribe this audio file accurately. Return only the transcribed text without any additional formatting or explanations.",
            file_contents=[audio_file]
        )
        
        transcription_response = await transcription_chat.send_message(transcription_message)
        transcript = transcription_response.strip()
        
        # Initialize LLM chat for summarization
        summary_chat = LlmChat(
            api_key=os.environ['EMERGENT_LLM_KEY'],
            session_id=f"summarize_{meeting_id}",
            system_message="You are a meeting summarization expert. Extract key points, decisions, and action items from meeting transcripts."
        ).with_model("openai", "gpt-4o-mini")
        
        # Create summarization prompt
        summary_prompt = f"""
        Please analyze this meeting transcript and provide:
        1. A concise summary (2-3 paragraphs)
        2. Key points discussed (bullet points)
        3. Decisions made (bullet points)
        4. Action items with responsible parties if mentioned (bullet points)

        Format your response as JSON with the following structure:
        {{
            "summary": "Brief summary text...",
            "key_points": ["Point 1", "Point 2", ...],
            "decisions": ["Decision 1", "Decision 2", ...],
            "action_items": ["Action 1", "Action 2", ...]
        }}

        Meeting Transcript:
        {transcript}
        """
        
        # Get summary
        logger.info(f"Generating summary for meeting {meeting_id}")
        summary_message = UserMessage(text=summary_prompt)
        summary_response = await summary_chat.send_message(summary_message)
        
        # Parse summary response with better JSON extraction
        import json
        import re
        
        try:
            # Try to extract JSON from markdown code blocks
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', summary_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find JSON without code blocks
                json_match = re.search(r'(\{.*\})', summary_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    json_str = summary_response
            
            summary_data = json.loads(json_str)
            summary_text = summary_data.get("summary", "")
            key_points = summary_data.get("key_points", []) + summary_data.get("decisions", [])
            action_items = summary_data.get("action_items", [])
        except (json.JSONDecodeError, AttributeError):
            # Fallback if JSON parsing fails
            summary_text = summary_response
            key_points = []
            action_items = []
        
        # Update meeting with results
        await db.meetings.update_one(
            {"id": meeting_id},
            {
                "$set": {
                    "transcript": transcript,
                    "summary": summary_text,
                    "key_points": key_points,
                    "action_items": action_items,
                    "processed_at": datetime.utcnow(),
                    "status": "completed"
                }
            }
        )
        
        logger.info(f"AI processing completed for meeting {meeting_id}")
        
    except Exception as e:
        logger.error(f"Error in AI processing for meeting {meeting_id}: {str(e)}")
        await db.meetings.update_one(
            {"id": meeting_id},
            {"$set": {"status": "error"}}
        )

@api_router.delete("/meetings/{meeting_id}")
async def delete_meeting(meeting_id: str):
    """Delete a meeting recording"""
    meeting = await db.meetings.find_one({"id": meeting_id})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    # Delete audio file if exists
    if meeting.get("audio_file_path"):
        try:
            os.remove(meeting["audio_file_path"])
        except OSError:
            pass  # File might not exist
    
    # Delete from database
    await db.meetings.delete_one({"id": meeting_id})
    
    return {"message": "Meeting deleted successfully"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()