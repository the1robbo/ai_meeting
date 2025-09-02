#!/usr/bin/env python3
"""
Backend Test Suite for AI-Powered Meeting Summarizer
Tests all backend API endpoints and AI processing workflow
"""

import requests
import json
import os
import time
import tempfile
import wave
import numpy as np
from pathlib import Path
import sys

# Get backend URL from frontend .env file
def get_backend_url():
    frontend_env_path = Path("/app/frontend/.env")
    if frontend_env_path.exists():
        with open(frontend_env_path, 'r') as f:
            for line in f:
                if line.startswith('EXPO_PUBLIC_BACKEND_URL='):
                    return line.split('=', 1)[1].strip()
    return "http://localhost:8001"

BASE_URL = get_backend_url() + "/api"
print(f"Testing backend at: {BASE_URL}")

class BackendTester:
    def __init__(self):
        self.session = requests.Session()
        self.test_meeting_id = None
        self.test_results = []
        
    def log_test(self, test_name, success, message="", details=None):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if message:
            print(f"   {message}")
        if details:
            print(f"   Details: {details}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "message": message,
            "details": details
        })
        print()

    def create_test_audio_file(self, duration=5, sample_rate=44100):
        """Create a test audio file with some audio content"""
        try:
            # Generate a simple sine wave audio
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            # Mix of different frequencies to simulate speech
            audio_data = (
                0.3 * np.sin(2 * np.pi * 440 * t) +  # A4 note
                0.2 * np.sin(2 * np.pi * 880 * t) +  # A5 note
                0.1 * np.sin(2 * np.pi * 220 * t)    # A3 note
            )
            
            # Convert to 16-bit integers
            audio_data = (audio_data * 32767).astype(np.int16)
            
            # Create temporary WAV file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
            
            with wave.open(temp_file.name, 'w') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 2 bytes per sample
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_data.tobytes())
            
            return temp_file.name
        except Exception as e:
            print(f"Warning: Could not create audio file with numpy/wave: {e}")
            # Fallback: create a minimal WAV file manually
            return self.create_minimal_wav_file()

    def create_minimal_wav_file(self):
        """Create a minimal valid WAV file as fallback"""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        
        # Minimal WAV header + some data
        wav_header = b'RIFF\x24\x08\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x08\x00\x00'
        # Add some sample audio data (silence)
        audio_data = b'\x00\x00' * 1000  # 1000 samples of silence
        
        with open(temp_file.name, 'wb') as f:
            f.write(wav_header + audio_data)
        
        return temp_file.name

    def test_api_health(self):
        """Test basic API connectivity"""
        try:
            response = self.session.get(f"{BASE_URL}/")
            if response.status_code == 200:
                data = response.json()
                self.log_test("API Health Check", True, f"API is responding: {data.get('message', 'OK')}")
                return True
            else:
                self.log_test("API Health Check", False, f"HTTP {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.log_test("API Health Check", False, f"Connection error: {str(e)}")
            return False

    def test_create_meeting(self):
        """Test meeting creation endpoint"""
        try:
            meeting_data = {
                "title": "Test Meeting - Backend Integration Test"
            }
            
            response = self.session.post(f"{BASE_URL}/meetings", json=meeting_data)
            
            if response.status_code == 200:
                data = response.json()
                self.test_meeting_id = data.get('id')
                
                # Verify required fields
                required_fields = ['id', 'title', 'created_at', 'status']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_test("Create Meeting", False, f"Missing fields: {missing_fields}", data)
                    return False
                
                if data.get('status') != 'recording':
                    self.log_test("Create Meeting", False, f"Expected status 'recording', got '{data.get('status')}'", data)
                    return False
                
                self.log_test("Create Meeting", True, f"Meeting created with ID: {self.test_meeting_id}")
                return True
            else:
                self.log_test("Create Meeting", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Create Meeting", False, f"Error: {str(e)}")
            return False

    def test_get_meetings(self):
        """Test meeting listing endpoint"""
        try:
            response = self.session.get(f"{BASE_URL}/meetings")
            
            if response.status_code == 200:
                data = response.json()
                
                if not isinstance(data, list):
                    self.log_test("Get Meetings List", False, "Response is not a list", data)
                    return False
                
                # Check if our test meeting is in the list
                if self.test_meeting_id:
                    meeting_found = any(meeting.get('id') == self.test_meeting_id for meeting in data)
                    if not meeting_found:
                        self.log_test("Get Meetings List", False, f"Test meeting {self.test_meeting_id} not found in list")
                        return False
                
                self.log_test("Get Meetings List", True, f"Retrieved {len(data)} meetings")
                return True
            else:
                self.log_test("Get Meetings List", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Get Meetings List", False, f"Error: {str(e)}")
            return False

    def test_get_single_meeting(self):
        """Test getting a specific meeting"""
        if not self.test_meeting_id:
            self.log_test("Get Single Meeting", False, "No test meeting ID available")
            return False
            
        try:
            response = self.session.get(f"{BASE_URL}/meetings/{self.test_meeting_id}")
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('id') != self.test_meeting_id:
                    self.log_test("Get Single Meeting", False, f"ID mismatch: expected {self.test_meeting_id}, got {data.get('id')}")
                    return False
                
                self.log_test("Get Single Meeting", True, f"Retrieved meeting: {data.get('title')}")
                return True
            else:
                self.log_test("Get Single Meeting", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Get Single Meeting", False, f"Error: {str(e)}")
            return False

    def test_audio_upload(self):
        """Test audio file upload endpoint"""
        if not self.test_meeting_id:
            self.log_test("Audio Upload", False, "No test meeting ID available")
            return False
            
        try:
            # Create test audio file
            audio_file_path = self.create_test_audio_file()
            
            with open(audio_file_path, 'rb') as audio_file:
                files = {'audio_file': ('test_audio.wav', audio_file, 'audio/wav')}
                response = self.session.post(f"{BASE_URL}/meetings/{self.test_meeting_id}/upload-audio", files=files)
            
            # Clean up temp file
            os.unlink(audio_file_path)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('meeting_id') != self.test_meeting_id:
                    self.log_test("Audio Upload", False, f"Meeting ID mismatch in response", data)
                    return False
                
                # Verify meeting status was updated
                meeting_response = self.session.get(f"{BASE_URL}/meetings/{self.test_meeting_id}")
                if meeting_response.status_code == 200:
                    meeting_data = meeting_response.json()
                    if meeting_data.get('status') != 'uploaded':
                        self.log_test("Audio Upload", False, f"Meeting status not updated to 'uploaded', got '{meeting_data.get('status')}'")
                        return False
                    
                    if not meeting_data.get('audio_file_path'):
                        self.log_test("Audio Upload", False, "Audio file path not set in meeting")
                        return False
                
                self.log_test("Audio Upload", True, "Audio file uploaded successfully")
                return True
            else:
                self.log_test("Audio Upload", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Audio Upload", False, f"Error: {str(e)}")
            return False

    def test_ai_processing(self):
        """Test AI processing endpoint (transcription + summarization)"""
        if not self.test_meeting_id:
            self.log_test("AI Processing", False, "No test meeting ID available")
            return False
            
        try:
            # Start AI processing
            response = self.session.post(f"{BASE_URL}/meetings/{self.test_meeting_id}/process")
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') != 'processing':
                    self.log_test("AI Processing", False, f"Expected status 'processing', got '{data.get('status')}'", data)
                    return False
                
                # Wait for processing to complete (with timeout)
                max_wait_time = 120  # 2 minutes
                wait_interval = 5    # 5 seconds
                elapsed_time = 0
                
                print(f"   Waiting for AI processing to complete (max {max_wait_time}s)...")
                
                while elapsed_time < max_wait_time:
                    time.sleep(wait_interval)
                    elapsed_time += wait_interval
                    
                    # Check meeting status
                    meeting_response = self.session.get(f"{BASE_URL}/meetings/{self.test_meeting_id}")
                    if meeting_response.status_code == 200:
                        meeting_data = meeting_response.json()
                        status = meeting_data.get('status')
                        
                        print(f"   Status after {elapsed_time}s: {status}")
                        
                        if status == 'completed':
                            # Verify AI processing results
                            transcript = meeting_data.get('transcript')
                            summary = meeting_data.get('summary')
                            
                            if not transcript:
                                self.log_test("AI Processing", False, "No transcript generated")
                                return False
                            
                            if not summary:
                                self.log_test("AI Processing", False, "No summary generated")
                                return False
                            
                            self.log_test("AI Processing", True, f"AI processing completed successfully. Transcript length: {len(transcript)} chars, Summary length: {len(summary)} chars")
                            return True
                            
                        elif status == 'error':
                            self.log_test("AI Processing", False, "AI processing failed with error status")
                            return False
                
                # Timeout reached
                self.log_test("AI Processing", False, f"AI processing timed out after {max_wait_time}s")
                return False
                
            else:
                self.log_test("AI Processing", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("AI Processing", False, f"Error: {str(e)}")
            return False

    def test_qa_before_processing(self):
        """Test Q&A endpoint before meeting is processed (should fail)"""
        if not self.test_meeting_id:
            self.log_test("Q&A Before Processing", False, "No test meeting ID available")
            return False
            
        try:
            # Create a new meeting that hasn't been processed
            meeting_data = {"title": "Test Meeting - Q&A Before Processing"}
            response = self.session.post(f"{BASE_URL}/meetings", json=meeting_data)
            
            if response.status_code != 200:
                self.log_test("Q&A Before Processing", False, "Failed to create test meeting")
                return False
                
            unprocessed_meeting_id = response.json().get('id')
            
            # Try to ask a question before processing
            question_data = {"question": "What were the main topics discussed?"}
            qa_response = self.session.post(f"{BASE_URL}/meetings/{unprocessed_meeting_id}/ask-question", json=question_data)
            
            # Clean up the test meeting
            self.session.delete(f"{BASE_URL}/meetings/{unprocessed_meeting_id}")
            
            if qa_response.status_code == 400:
                error_data = qa_response.json()
                if "must be processed" in error_data.get('detail', '').lower():
                    self.log_test("Q&A Before Processing", True, "Correctly rejected Q&A for unprocessed meeting")
                    return True
                else:
                    self.log_test("Q&A Before Processing", False, f"Wrong error message: {error_data.get('detail')}")
                    return False
            else:
                self.log_test("Q&A Before Processing", False, f"Expected HTTP 400, got {qa_response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Q&A Before Processing", False, f"Error: {str(e)}")
            return False

    def test_qa_nonexistent_meeting(self):
        """Test Q&A endpoint with non-existent meeting (should fail)"""
        try:
            fake_meeting_id = "nonexistent-meeting-id-12345"
            question_data = {"question": "What were the main topics discussed?"}
            
            response = self.session.post(f"{BASE_URL}/meetings/{fake_meeting_id}/ask-question", json=question_data)
            
            if response.status_code == 404:
                error_data = response.json()
                if "not found" in error_data.get('detail', '').lower():
                    self.log_test("Q&A Non-existent Meeting", True, "Correctly rejected Q&A for non-existent meeting")
                    return True
                else:
                    self.log_test("Q&A Non-existent Meeting", False, f"Wrong error message: {error_data.get('detail')}")
                    return False
            else:
                self.log_test("Q&A Non-existent Meeting", False, f"Expected HTTP 404, got {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Q&A Non-existent Meeting", False, f"Error: {str(e)}")
            return False

    def test_qa_functionality(self):
        """Test Q&A functionality with processed meeting"""
        if not self.test_meeting_id:
            self.log_test("Q&A Functionality", False, "No test meeting ID available")
            return False
            
        try:
            # First verify the meeting is processed
            meeting_response = self.session.get(f"{BASE_URL}/meetings/{self.test_meeting_id}")
            if meeting_response.status_code != 200:
                self.log_test("Q&A Functionality", False, "Could not retrieve meeting")
                return False
                
            meeting_data = meeting_response.json()
            if meeting_data.get('status') != 'completed':
                self.log_test("Q&A Functionality", False, f"Meeting not processed (status: {meeting_data.get('status')})")
                return False
            
            # Test multiple questions
            test_questions = [
                "What were the main topics discussed in this meeting?",
                "What action items were identified?",
                "Can you summarize the key decisions made?",
                "What were the key points from this meeting?"
            ]
            
            successful_questions = 0
            
            for i, question_text in enumerate(test_questions):
                question_data = {"question": question_text}
                response = self.session.post(f"{BASE_URL}/meetings/{self.test_meeting_id}/ask-question", json=question_data)
                
                if response.status_code == 200:
                    qa_data = response.json()
                    
                    # Validate response format
                    required_fields = ['question', 'answer', 'timestamp']
                    missing_fields = [field for field in required_fields if field not in qa_data]
                    
                    if missing_fields:
                        self.log_test("Q&A Functionality", False, f"Question {i+1}: Missing fields {missing_fields}")
                        continue
                    
                    if qa_data.get('question') != question_text:
                        self.log_test("Q&A Functionality", False, f"Question {i+1}: Question mismatch")
                        continue
                    
                    if not qa_data.get('answer') or len(qa_data.get('answer', '').strip()) < 10:
                        self.log_test("Q&A Functionality", False, f"Question {i+1}: Answer too short or empty")
                        continue
                    
                    # Validate timestamp format
                    timestamp = qa_data.get('timestamp')
                    if not timestamp:
                        self.log_test("Q&A Functionality", False, f"Question {i+1}: Missing timestamp")
                        continue
                    
                    successful_questions += 1
                    print(f"   Q{i+1}: {question_text[:50]}...")
                    print(f"   A{i+1}: {qa_data.get('answer')[:100]}...")
                    
                else:
                    print(f"   Question {i+1} failed: HTTP {response.status_code}")
            
            if successful_questions == len(test_questions):
                self.log_test("Q&A Functionality", True, f"All {successful_questions} questions answered successfully")
                return True
            elif successful_questions > 0:
                self.log_test("Q&A Functionality", False, f"Only {successful_questions}/{len(test_questions)} questions succeeded")
                return False
            else:
                self.log_test("Q&A Functionality", False, "No questions were answered successfully")
                return False
                
        except Exception as e:
            self.log_test("Q&A Functionality", False, f"Error: {str(e)}")
            return False

    def test_qa_storage_verification(self):
        """Test that Q&A entries are properly stored in the database"""
        if not self.test_meeting_id:
            self.log_test("Q&A Storage Verification", False, "No test meeting ID available")
            return False
            
        try:
            # Ask a specific question
            test_question = "What is the main purpose of this meeting?"
            question_data = {"question": test_question}
            
            response = self.session.post(f"{BASE_URL}/meetings/{self.test_meeting_id}/ask-question", json=question_data)
            
            if response.status_code != 200:
                self.log_test("Q&A Storage Verification", False, f"Failed to ask question: HTTP {response.status_code}")
                return False
            
            qa_response = response.json()
            
            # Retrieve the meeting and check if Q&A is stored
            meeting_response = self.session.get(f"{BASE_URL}/meetings/{self.test_meeting_id}")
            
            if meeting_response.status_code != 200:
                self.log_test("Q&A Storage Verification", False, "Failed to retrieve meeting")
                return False
            
            meeting_data = meeting_response.json()
            questions_answers = meeting_data.get('questions_answers', [])
            
            if not questions_answers:
                self.log_test("Q&A Storage Verification", False, "No Q&A entries found in meeting")
                return False
            
            # Find our specific question
            found_qa = None
            for qa in questions_answers:
                if qa.get('question') == test_question:
                    found_qa = qa
                    break
            
            if not found_qa:
                self.log_test("Q&A Storage Verification", False, f"Question '{test_question}' not found in stored Q&A")
                return False
            
            # Verify the stored Q&A matches the response
            if found_qa.get('answer') != qa_response.get('answer'):
                self.log_test("Q&A Storage Verification", False, "Stored answer doesn't match response")
                return False
            
            # Verify all Q&A entries have required fields
            for i, qa in enumerate(questions_answers):
                required_fields = ['question', 'answer', 'timestamp']
                missing_fields = [field for field in required_fields if field not in qa]
                
                if missing_fields:
                    self.log_test("Q&A Storage Verification", False, f"Q&A entry {i+1} missing fields: {missing_fields}")
                    return False
            
            self.log_test("Q&A Storage Verification", True, f"Q&A properly stored. Total entries: {len(questions_answers)}")
            return True
            
        except Exception as e:
            self.log_test("Q&A Storage Verification", False, f"Error: {str(e)}")
            return False

    def test_qa_integration_workflow(self):
        """Test complete Q&A integration workflow"""
        try:
            # Create a new meeting for integration test
            meeting_data = {"title": "Integration Test Meeting - Q&A Workflow"}
            response = self.session.post(f"{BASE_URL}/meetings", json=meeting_data)
            
            if response.status_code != 200:
                self.log_test("Q&A Integration Workflow", False, "Failed to create integration test meeting")
                return False
            
            integration_meeting_id = response.json().get('id')
            
            try:
                # Upload audio
                audio_file_path = self.create_test_audio_file()
                
                with open(audio_file_path, 'rb') as audio_file:
                    files = {'audio_file': ('integration_test.wav', audio_file, 'audio/wav')}
                    upload_response = self.session.post(f"{BASE_URL}/meetings/{integration_meeting_id}/upload-audio", files=files)
                
                os.unlink(audio_file_path)
                
                if upload_response.status_code != 200:
                    self.log_test("Q&A Integration Workflow", False, "Failed to upload audio for integration test")
                    return False
                
                # Process with AI
                process_response = self.session.post(f"{BASE_URL}/meetings/{integration_meeting_id}/process")
                
                if process_response.status_code != 200:
                    self.log_test("Q&A Integration Workflow", False, "Failed to start AI processing for integration test")
                    return False
                
                # Wait for processing to complete
                max_wait_time = 120
                wait_interval = 5
                elapsed_time = 0
                
                print("   Waiting for AI processing to complete for integration test...")
                
                while elapsed_time < max_wait_time:
                    time.sleep(wait_interval)
                    elapsed_time += wait_interval
                    
                    meeting_response = self.session.get(f"{BASE_URL}/meetings/{integration_meeting_id}")
                    if meeting_response.status_code == 200:
                        meeting_data = meeting_response.json()
                        status = meeting_data.get('status')
                        
                        if status == 'completed':
                            # Now test Q&A on the processed meeting
                            question_data = {"question": "What can you tell me about this meeting?"}
                            qa_response = self.session.post(f"{BASE_URL}/meetings/{integration_meeting_id}/ask-question", json=question_data)
                            
                            if qa_response.status_code == 200:
                                qa_data = qa_response.json()
                                
                                # Verify the Q&A response uses meeting context
                                answer = qa_data.get('answer', '').lower()
                                meeting_context_indicators = ['meeting', 'transcript', 'summary', 'discussed']
                                
                                has_context = any(indicator in answer for indicator in meeting_context_indicators)
                                
                                if has_context:
                                    self.log_test("Q&A Integration Workflow", True, "Complete workflow successful: create → upload → process → Q&A")
                                    return True
                                else:
                                    self.log_test("Q&A Integration Workflow", False, "Q&A answer doesn't seem to use meeting context")
                                    return False
                            else:
                                self.log_test("Q&A Integration Workflow", False, f"Q&A failed: HTTP {qa_response.status_code}")
                                return False
                        
                        elif status == 'error':
                            self.log_test("Q&A Integration Workflow", False, "AI processing failed for integration test")
                            return False
                
                self.log_test("Q&A Integration Workflow", False, "AI processing timed out for integration test")
                return False
                
            finally:
                # Clean up integration test meeting
                self.session.delete(f"{BASE_URL}/meetings/{integration_meeting_id}")
                
        except Exception as e:
            self.log_test("Q&A Integration Workflow", False, f"Error: {str(e)}")
            return False

    def test_delete_meeting(self):
        """Test meeting deletion endpoint"""
        if not self.test_meeting_id:
            self.log_test("Delete Meeting", False, "No test meeting ID available")
            return False
            
        try:
            response = self.session.delete(f"{BASE_URL}/meetings/{self.test_meeting_id}")
            
            if response.status_code == 200:
                # Verify meeting is actually deleted
                get_response = self.session.get(f"{BASE_URL}/meetings/{self.test_meeting_id}")
                if get_response.status_code == 404:
                    self.log_test("Delete Meeting", True, "Meeting deleted successfully")
                    return True
                else:
                    self.log_test("Delete Meeting", False, "Meeting still exists after deletion")
                    return False
            else:
                self.log_test("Delete Meeting", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Delete Meeting", False, f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all backend tests in sequence"""
        print("=" * 60)
        print("AI-POWERED MEETING SUMMARIZER - BACKEND TEST SUITE")
        print("=" * 60)
        print()
        
        # Test sequence
        tests = [
            ("API Health Check", self.test_api_health),
            ("Create Meeting", self.test_create_meeting),
            ("Get Meetings List", self.test_get_meetings),
            ("Get Single Meeting", self.test_get_single_meeting),
            ("Audio Upload", self.test_audio_upload),
            ("AI Processing (Gemini + GPT-4)", self.test_ai_processing),
            ("Delete Meeting", self.test_delete_meeting),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            success = test_func()
            if success:
                passed += 1
        
        print("=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        print()
        
        # Detailed results
        print("DETAILED RESULTS:")
        for result in self.test_results:
            status = "✅" if result["success"] else "❌"
            print(f"{status} {result['test']}")
            if result["message"]:
                print(f"   {result['message']}")
        
        return passed == total

def main():
    """Main test execution"""
    tester = BackendTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n🎉 All backend tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some backend tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()