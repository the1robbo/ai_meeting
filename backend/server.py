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
    company_name: Optional[str] = None
    participants: Optional[List[str]] = []
    meeting_date: Optional[datetime] = None
    audio_file_path: Optional[str] = None
    transcript: Optional[str] = None
    raw_transcript: Optional[str] = None  # Original transcript before diarization
    summary: Optional[str] = None
    key_points: Optional[List[str]] = None
    action_items: Optional[List[str]] = None
    questions_answers: Optional[List[QuestionAnswer]] = []
    processing_progress: Optional[int] = 0  # Progress percentage (0-100)
    processing_stage: Optional[str] = "idle"  # idle, uploading, transcribing, diarizing, summarizing, completed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    status: str = "recording"  # recording, processing, completed, error

class MeetingCreate(BaseModel):
    title: str

class QuestionCreate(BaseModel):
    question: str

class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    company_name: Optional[str] = None
    participants: Optional[List[str]] = None
    meeting_date: Optional[datetime] = None

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
    """Background task to process audio with AI including speaker diarization"""
    try:
        logger.info(f"Starting AI processing for meeting {meeting_id}")
        
        # First, let's use Gemini for transcription (it supports audio files)
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
        raw_transcript = transcription_response.strip()
        
        # Now perform speaker diarization using AI analysis
        logger.info(f"Performing speaker diarization for meeting {meeting_id}")
        diarization_chat = LlmChat(
            api_key=os.environ['EMERGENT_LLM_KEY'],
            session_id=f"diarize_{meeting_id}",
            system_message="""You are a speaker diarization expert. Analyze the transcript and identify different speakers based on:
1. Speaking patterns and style changes
2. Topic transitions that suggest speaker changes
3. Conversational cues like responses, questions, and interruptions
4. Natural speech flow patterns

Format the output with speaker labels like:
Person 1: [their speech]
Person 2: [their speech]
Person 1: [their speech continues]

If you cannot clearly identify speaker changes, use your best judgment based on natural conversation flow."""
        ).with_model("openai", "gpt-4o")
        
        diarization_prompt = f"""
        Please analyze this meeting transcript and identify different speakers. Add speaker labels (Person 1, Person 2, etc.) to create a diarized transcript.

        Look for natural conversation patterns, topic changes, questions and responses, and speaking style differences to identify when different people are speaking.

        Original Transcript:
        {raw_transcript}

        Please return the diarized transcript with clear speaker labels:
        """
        
        diarization_message = UserMessage(text=diarization_prompt)
        diarized_transcript = await diarization_chat.send_message(diarization_message)
        transcript = diarized_transcript.strip()
        
        # Initialize LLM chat for summarization using the diarized transcript
        summary_chat = LlmChat(
            api_key=os.environ['EMERGENT_LLM_KEY'],
            session_id=f"summarize_{meeting_id}",
            system_message="You are a meeting summarization expert. Extract key points, decisions, and action items from meeting transcripts with speaker identification."
        ).with_model("openai", "gpt-4o-mini")
        
        # Create summarization prompt with speaker context
        summary_prompt = f"""
        Please analyze this diarized meeting transcript and provide:
        1. A concise summary (2-3 paragraphs) mentioning key participants
        2. Key points discussed (bullet points) - include who said what when relevant
        3. Decisions made (bullet points) - note who made decisions
        4. Action items with responsible parties (bullet points)

        Format your response as JSON with the following structure:
        {{
            "summary": "Brief summary text mentioning speakers...",
            "key_points": ["Person 1 discussed X", "Person 2 mentioned Y", ...],
            "decisions": ["Person 1 decided Z", "Group agreed on W", ...],
            "action_items": ["Person 1 will do X by date", "Person 2 to follow up on Y", ...]
        }}

        Diarized Meeting Transcript:
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
        
        # Update meeting with results - store both raw and diarized transcripts
        await db.meetings.update_one(
            {"id": meeting_id},
            {
                "$set": {
                    "transcript": transcript,  # Use diarized version as main transcript
                    "raw_transcript": raw_transcript,   # Keep original for reference
                    "summary": summary_text,
                    "key_points": key_points,
                    "action_items": action_items,
                    "processed_at": datetime.utcnow(),
                    "status": "completed"
                }
            }
        )
        
        logger.info(f"AI processing with speaker diarization completed for meeting {meeting_id}")
        
    except Exception as e:
        logger.error(f"Error in AI processing for meeting {meeting_id}: {str(e)}")
        await db.meetings.update_one(
            {"id": meeting_id},
            {"$set": {"status": "error"}}
        )

@api_router.put("/meetings/{meeting_id}")
async def update_meeting(meeting_id: str, meeting_update: MeetingUpdate):
    """Update meeting metadata (title, company, participants, date)"""
    try:
        # Get meeting
        meeting = await db.meetings.find_one({"id": meeting_id})
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        # Prepare update data (only include non-None values)
        update_data = {}
        if meeting_update.title is not None:
            update_data["title"] = meeting_update.title
        if meeting_update.company_name is not None:
            update_data["company_name"] = meeting_update.company_name
        if meeting_update.participants is not None:
            update_data["participants"] = meeting_update.participants
        if meeting_update.meeting_date is not None:
            update_data["meeting_date"] = meeting_update.meeting_date
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Update meeting in database
        await db.meetings.update_one(
            {"id": meeting_id},
            {"$set": update_data}
        )
        
        # Return updated meeting
        updated_meeting = await db.meetings.find_one({"id": meeting_id})
        return MeetingRecording(**updated_meeting)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating meeting {meeting_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating meeting: {str(e)}")

@api_router.post("/meetings/{meeting_id}/ask-question")
async def ask_question_about_meeting(meeting_id: str, question_data: QuestionCreate):
    """Ask a question about a meeting and get AI-powered answer based on meeting content"""
    try:
        # Get meeting
        meeting = await db.meetings.find_one({"id": meeting_id})
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        if meeting.get("status") != "completed":
            raise HTTPException(status_code=400, detail="Meeting must be processed before asking questions")
        
        # Prepare context from meeting content
        context_parts = []
        
        if meeting.get("summary"):
            context_parts.append(f"Summary: {meeting['summary']}")
        
        if meeting.get("transcript"):
            context_parts.append(f"Full Transcript: {meeting['transcript']}")
        
        if meeting.get("key_points"):
            context_parts.append(f"Key Points: {', '.join(meeting['key_points'])}")
        
        if meeting.get("action_items"):
            context_parts.append(f"Action Items: {', '.join(meeting['action_items'])}")
        
        if not context_parts:
            raise HTTPException(status_code=400, detail="No meeting content available to answer questions")
        
        meeting_context = "\n\n".join(context_parts)
        
        # Initialize LLM chat for question answering
        qa_chat = LlmChat(
            api_key=os.environ['EMERGENT_LLM_KEY'],
            session_id=f"qa_{meeting_id}_{datetime.utcnow().timestamp()}",
            system_message="You are a helpful assistant that answers questions about meeting content. Base your answers strictly on the provided meeting information. If you cannot answer based on the available information, say so clearly."
        ).with_model("openai", "gpt-4o-mini")
        
        # Create question prompt
        question_prompt = f"""
        Based on the following meeting information, please answer the user's question:

        Meeting Information:
        {meeting_context}

        User Question: {question_data.question}

        Please provide a helpful and accurate answer based only on the meeting information provided above. If the question cannot be answered from the available information, please state that clearly.
        """
        
        # Get answer from AI
        logger.info(f"Processing question for meeting {meeting_id}: {question_data.question}")
        question_message = UserMessage(text=question_prompt)
        answer_response = await qa_chat.send_message(question_message)
        
        # Create Q&A object
        qa_entry = QuestionAnswer(
            question=question_data.question,
            answer=answer_response.strip()
        )
        
        # Add Q&A to meeting
        existing_qas = meeting.get("questions_answers", [])
        existing_qas.append(qa_entry.dict())
        
        await db.meetings.update_one(
            {"id": meeting_id},
            {"$set": {"questions_answers": existing_qas}}
        )
        
        logger.info(f"Question answered for meeting {meeting_id}")
        
        return qa_entry
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing question for meeting {meeting_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")

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