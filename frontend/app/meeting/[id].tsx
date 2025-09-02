import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
  SafeAreaView,
  StatusBar,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

interface QuestionAnswer {
  question: string;
  answer: string;
  timestamp: string;
}

interface Meeting {
  id: string;
  title: string;
  company_name?: string;
  participants?: string[];
  meeting_date?: string;
  transcript?: string;
  summary?: string;
  key_points?: string[];
  action_items?: string[];
  questions_answers?: QuestionAnswer[];
  created_at: string;
  processed_at?: string;
  status: 'recording' | 'uploaded' | 'processing' | 'completed' | 'error';
}

export default function MeetingDetails() {
  const { id } = useLocalSearchParams();
  const router = useRouter();
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [loading, setLoading] = useState(true);
  const [question, setQuestion] = useState('');
  const [askingQuestion, setAskingQuestion] = useState(false);
  
  // Edit mode states
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editCompany, setEditCompany] = useState('');
  const [editParticipants, setEditParticipants] = useState('');
  const [editDate, setEditDate] = useState('');
  const [savingChanges, setSavingChanges] = useState(false);

  const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

  useEffect(() => {
    loadMeeting();
  }, [id]);

  useEffect(() => {
    // Initialize edit fields when meeting loads
    if (meeting) {
      setEditTitle(meeting.title || '');
      setEditCompany(meeting.company_name || '');
      setEditParticipants(meeting.participants?.join(', ') || '');
      setEditDate(meeting.meeting_date ? new Date(meeting.meeting_date).toISOString().split('T')[0] : '');
    }
  }, [meeting]);

  const loadMeeting = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${BACKEND_URL}/api/meetings/${id}`);
      if (response.ok) {
        const meetingData = await response.json();
        setMeeting(meetingData);
      } else {
        Alert.alert('Error', 'Meeting not found');
        router.back();
      }
    } catch (error) {
      console.error('Error loading meeting:', error);
      Alert.alert('Error', 'Failed to load meeting details');
    } finally {
      setLoading(false);
    }
  };

  const startEditing = () => {
    setIsEditing(true);
  };

  const cancelEditing = () => {
    setIsEditing(false);
    // Reset edit fields to current meeting values
    if (meeting) {
      setEditTitle(meeting.title || '');
      setEditCompany(meeting.company_name || '');
      setEditParticipants(meeting.participants?.join(', ') || '');
      setEditDate(meeting.meeting_date ? new Date(meeting.meeting_date).toISOString().split('T')[0] : '');
    }
  };

  const saveChanges = async () => {
    if (!meeting || !editTitle.trim()) {
      Alert.alert('Error', 'Meeting title is required');
      return;
    }

    try {
      setSavingChanges(true);
      
      const updateData: any = {
        title: editTitle.trim(),
        company_name: editCompany.trim() || null,
        participants: editParticipants.trim() ? editParticipants.split(',').map(p => p.trim()).filter(p => p) : [],
      };

      if (editDate) {
        updateData.meeting_date = new Date(editDate).toISOString();
      }

      const response = await fetch(`${BACKEND_URL}/api/meetings/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(updateData),
      });

      if (response.ok) {
        const updatedMeeting = await response.json();
        setMeeting(updatedMeeting);
        setIsEditing(false);
        Alert.alert('Success', 'Meeting details updated successfully');
      } else {
        const errorData = await response.json();
        Alert.alert('Error', errorData.detail || 'Failed to update meeting');
      }
    } catch (error) {
      console.error('Error saving changes:', error);
      Alert.alert('Error', 'Failed to update meeting details');
    } finally {
      setSavingChanges(false);
    }
  };

  const askQuestion = async () => {
    if (!question.trim()) {
      Alert.alert('Error', 'Please enter a question');
      return;
    }

    if (!meeting || meeting.status !== 'completed') {
      Alert.alert('Error', 'Meeting must be processed before asking questions');
      return;
    }

    try {
      setAskingQuestion(true);
      const response = await fetch(`${BACKEND_URL}/api/meetings/${id}/ask-question`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question: question.trim() }),
      });

      if (response.ok) {
        const questionAnswer = await response.json();
        
        // Update local meeting data
        const updatedMeeting = {
          ...meeting,
          questions_answers: [
            ...(meeting.questions_answers || []),
            questionAnswer,
          ],
        };
        setMeeting(updatedMeeting);
        setQuestion('');
      } else {
        const errorData = await response.json();
        Alert.alert('Error', errorData.detail || 'Failed to ask question');
      }
    } catch (error) {
      console.error('Error asking question:', error);
      Alert.alert('Error', 'Failed to ask question');
    } finally {
      setAskingQuestion(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <StatusBar barStyle="light-content" />
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#007AFF" />
          <Text style={styles.loadingText}>Loading meeting details...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!meeting) {
    return (
      <SafeAreaView style={styles.container}>
        <StatusBar barStyle="light-content" />
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>Meeting not found</Text>
          <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
            <Text style={styles.backButtonText}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" />
      
      <KeyboardAvoidingView 
        style={styles.keyboardAvoidingView}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backIcon}>
            <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
          </TouchableOpacity>
          <Text style={styles.headerTitle} numberOfLines={1}>
            {meeting.title}
          </Text>
          <View style={[styles.statusBadge, { backgroundColor: getStatusColor(meeting.status) }]}>
            <Text style={styles.statusText}>{meeting.status}</Text>
          </View>
        </View>

        <ScrollView style={styles.scrollView} showsVerticalScrollIndicator={false}>
          {meeting.status === 'completed' ? (
            <>
              {/* Summary Section */}
              {meeting.summary && (
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Summary</Text>
                  <Text style={styles.summaryText}>{meeting.summary}</Text>
                </View>
              )}

              {/* Key Points Section */}
              {meeting.key_points && meeting.key_points.length > 0 && (
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Key Points</Text>
                  {meeting.key_points.map((point, index) => (
                    <View key={index} style={styles.bulletPoint}>
                      <Text style={styles.bullet}>•</Text>
                      <Text style={styles.bulletText}>{point}</Text>
                    </View>
                  ))}
                </View>
              )}

              {/* Action Items Section */}
              {meeting.action_items && meeting.action_items.length > 0 && (
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Action Items</Text>
                  {meeting.action_items.map((item, index) => (
                    <View key={index} style={styles.bulletPoint}>
                      <Text style={styles.bullet}>•</Text>
                      <Text style={styles.bulletText}>{item}</Text>
                    </View>
                  ))}
                </View>
              )}

              {/* Questions & Answers Section */}
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Questions & Answers</Text>
                
                {meeting.questions_answers && meeting.questions_answers.length > 0 && (
                  <View style={styles.qaList}>
                    {meeting.questions_answers.map((qa, index) => (
                      <View key={index} style={styles.qaItem}>
                        <View style={styles.questionContainer}>
                          <Ionicons name="help-circle" size={16} color="#007AFF" />
                          <Text style={styles.questionText}>{qa.question}</Text>
                        </View>
                        <View style={styles.answerContainer}>
                          <Ionicons name="checkmark-circle" size={16} color="#34C759" />
                          <Text style={styles.answerText}>{qa.answer}</Text>
                        </View>
                      </View>
                    ))}
                  </View>
                )}

                {/* Question Input */}
                <View style={styles.questionInputContainer}>
                  <TextInput
                    style={styles.questionInput}
                    value={question}
                    onChangeText={setQuestion}
                    placeholder="Ask a question about this meeting..."
                    placeholderTextColor="#8E8E93"
                    multiline
                  />
                  <TouchableOpacity
                    style={[styles.askButton, (!question.trim() || askingQuestion) && styles.askButtonDisabled]}
                    onPress={askQuestion}
                    disabled={!question.trim() || askingQuestion}
                  >
                    {askingQuestion ? (
                      <ActivityIndicator size="small" color="#FFFFFF" />
                    ) : (
                      <Ionicons name="send" size={20} color="#FFFFFF" />
                    )}
                  </TouchableOpacity>
                </View>
              </View>

              {/* Transcript Section (Collapsible) */}
              {meeting.transcript && (
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Full Transcript</Text>
                  <View style={styles.transcriptContainer}>
                    <Text style={styles.transcriptText}>{meeting.transcript}</Text>
                  </View>
                </View>
              )}
            </>
          ) : (
            <View style={styles.processingContainer}>
              <ActivityIndicator size="large" color="#007AFF" />
              <Text style={styles.processingText}>
                {meeting.status === 'processing' 
                  ? 'Processing meeting...' 
                  : 'Meeting not processed yet'}
              </Text>
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const getStatusColor = (status: string) => {
  switch (status) {
    case 'completed':
      return '#34C759';
    case 'processing':
      return '#FF9500';
    case 'error':
      return '#FF3B30';
    default:
      return '#8E8E93';
  }
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000000',
  },
  keyboardAvoidingView: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#333333',
  },
  backIcon: {
    marginRight: 12,
  },
  headerTitle: {
    flex: 1,
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
    marginRight: 12,
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 12,
    fontWeight: '500',
    color: '#FFFFFF',
    textTransform: 'capitalize',
  },
  scrollView: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    fontSize: 16,
    color: '#8E8E93',
    marginTop: 12,
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  errorText: {
    fontSize: 18,
    color: '#FF3B30',
    marginBottom: 20,
    textAlign: 'center',
  },
  backButton: {
    backgroundColor: '#007AFF',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 8,
  },
  backButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  section: {
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#333333',
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 12,
  },
  summaryText: {
    fontSize: 16,
    color: '#E5E5E7',
    lineHeight: 24,
  },
  bulletPoint: {
    flexDirection: 'row',
    marginBottom: 8,
    alignItems: 'flex-start',
  },
  bullet: {
    fontSize: 16,
    color: '#007AFF',
    marginRight: 8,
    marginTop: 2,
  },
  bulletText: {
    flex: 1,
    fontSize: 16,
    color: '#E5E5E7',
    lineHeight: 22,
  },
  qaList: {
    marginBottom: 20,
  },
  qaItem: {
    marginBottom: 16,
    padding: 12,
    backgroundColor: '#1C1C1E',
    borderRadius: 8,
  },
  questionContainer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  questionText: {
    flex: 1,
    fontSize: 14,
    color: '#007AFF',
    fontWeight: '500',
    marginLeft: 8,
    lineHeight: 20,
  },
  answerContainer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  answerText: {
    flex: 1,
    fontSize: 14,
    color: '#E5E5E7',
    marginLeft: 8,
    lineHeight: 20,
  },
  questionInputContainer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    backgroundColor: '#1C1C1E',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
    marginBottom: 8,
  },
  questionInput: {
    flex: 1,
    fontSize: 16,
    color: '#FFFFFF',
    maxHeight: 100,
    minHeight: 40,
    marginRight: 8,
  },
  askButton: {
    backgroundColor: '#007AFF',
    width: 36,
    height: 36,
    borderRadius: 18,
    justifyContent: 'center',
    alignItems: 'center',
  },
  askButtonDisabled: {
    backgroundColor: '#8E8E93',
  },
  transcriptContainer: {
    backgroundColor: '#1C1C1E',
    borderRadius: 8,
    padding: 12,
  },
  transcriptText: {
    fontSize: 14,
    color: '#E5E5E7',
    lineHeight: 20,
  },
  processingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 60,
  },
  processingText: {
    fontSize: 16,
    color: '#8E8E93',
    marginTop: 12,
    textAlign: 'center',
  },
});