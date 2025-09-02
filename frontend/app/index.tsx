import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  StatusBar,
  ActivityIndicator,
  Platform,
  Animated,
} from 'react-native';
import { Audio } from 'expo-av';
import * as FileSystem from 'expo-file-system';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Swipeable } from 'react-native-gesture-handler';
import CustomAlert from '../components/CustomAlert';
import { useCustomAlert } from '../hooks/useCustomAlert';

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
  created_at: string;
  processed_at?: string;
  status: 'recording' | 'uploaded' | 'processing' | 'completed' | 'error';
}

export default function Index() {
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [hasPermission, setHasPermission] = useState(false);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { alertConfig, visible, showAlert, hideAlert } = useCustomAlert();

  const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

  // Timer for recording duration
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isRecording && !isPaused) {
      interval = setInterval(() => {
        setRecordingDuration(prev => prev + 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isRecording, isPaused]);

  useEffect(() => {
    requestPermissions();
    loadMeetings();
  }, []);

  const requestPermissions = async () => {
    try {
      const { status } = await Audio.requestPermissionsAsync();
      setHasPermission(status === 'granted');
      
      if (status !== 'granted') {
        showAlert(
          'Permission Required',
          'This app needs microphone access to record meetings.',
          [{ text: 'OK' }]
        );
      }
    } catch (error) {
      console.error('Error requesting permissions:', error);
    }
  };

  const loadMeetings = async () => {
    try {
      // Load from local storage first for offline capability
      const storedMeetings = await AsyncStorage.getItem('meetings');
      if (storedMeetings) {
        setMeetings(JSON.parse(storedMeetings));
      }

      // Then sync with backend
      const response = await fetch(`${BACKEND_URL}/api/meetings`);
      if (response.ok) {
        const serverMeetings = await response.json();
        setMeetings(serverMeetings);
        await AsyncStorage.setItem('meetings', JSON.stringify(serverMeetings));
      }
    } catch (error) {
      console.error('Error loading meetings:', error);
    }
  };

  const startRecording = async () => {
    if (!hasPermission) {
      await requestPermissions();
      return;
    }

    try {
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const { recording: newRecording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      );

      setRecording(newRecording);
      setIsRecording(true);
      setIsPaused(false);
      setRecordingDuration(0);
    } catch (error) {
      console.error('Failed to start recording', error);
      showAlert('Error', 'Failed to start recording');
    }
  };

  const pauseRecording = async () => {
    if (!recording) return;

    try {
      await recording.pauseAsync();
      setIsPaused(true);
    } catch (error) {
      console.error('Failed to pause recording', error);
      showAlert('Error', 'Failed to pause recording');
    }
  };

  const resumeRecording = async () => {
    if (!recording) return;

    try {
      await recording.startAsync();
      setIsPaused(false);
    } catch (error) {
      console.error('Failed to resume recording', error);
      showAlert('Error', 'Failed to resume recording');
    }
  };

  const stopRecording = async () => {
    if (!recording) return;

    try {
      setIsRecording(false);
      setIsPaused(false);
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      
      if (uri) {
        await processRecording(uri);
      }
      
      setRecording(null);
      setRecordingDuration(0);
    } catch (error) {
      console.error('Failed to stop recording', error);
      showAlert('Error', 'Failed to stop recording');
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const processRecording = async (audioUri: string) => {
    setIsProcessing(true);
    
    try {
      // Create a new meeting
      const meetingTitle = `Meeting ${new Date().toLocaleString()}`;
      const createResponse = await fetch(`${BACKEND_URL}/api/meetings`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ title: meetingTitle }),
      });

      if (!createResponse.ok) {
        throw new Error('Failed to create meeting');
      }

      const meeting = await createResponse.json();

      // Upload audio file
      const formData = new FormData();
      formData.append('audio_file', {
        uri: audioUri,
        type: 'audio/wav',
        name: 'recording.wav',
      } as any);

      const uploadResponse = await fetch(
        `${BACKEND_URL}/api/meetings/${meeting.id}/upload-audio`,
        {
          method: 'POST',
          body: formData,
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }
      );

      if (!uploadResponse.ok) {
        throw new Error('Failed to upload audio');
      }

      // Start processing
      const processResponse = await fetch(
        `${BACKEND_URL}/api/meetings/${meeting.id}/process`,
        {
          method: 'POST',
        }
      );

      if (!processResponse.ok) {
        throw new Error('Failed to start processing');
      }

      showAlert(
        'Processing Started',
        'Your meeting is being processed. This may take a few minutes.',
        [{ text: 'OK' }]
      );

      // Poll for completion
      pollMeetingStatus(meeting.id);
      
    } catch (error) {
      console.error('Error processing recording:', error);
      showAlert('Error', 'Failed to process recording');
    } finally {
      setIsProcessing(false);
    }
  };

  const pollMeetingStatus = async (meetingId: string) => {
    const maxAttempts = 30; // 5 minutes max
    let attempts = 0;

    const poll = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/meetings/${meetingId}`);
        if (response.ok) {
          const meeting = await response.json();
          
          if (meeting.status === 'completed') {
            await loadMeetings();
            showAlert(
              'Processing Complete',
              'Your meeting has been transcribed and summarized!',
              [{ text: 'OK' }]
            );
            return;
          } else if (meeting.status === 'error') {
            showAlert('Error', 'Failed to process meeting');
            return;
          }
        }

        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 10000); // Poll every 10 seconds
        } else {
          showAlert('Timeout', 'Processing is taking longer than expected');
        }
      } catch (error) {
        console.error('Error polling status:', error);
      }
    };

    poll();
  };

  const deleteMeeting = async (meetingId: string, meetingTitle: string) => {
    showAlert(
      'Delete Meeting',
      `Are you sure you want to delete "${meetingTitle}"? This action cannot be undone.`,
      [
        {
          text: 'Cancel',
          style: 'cancel',
        },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              const response = await fetch(`${BACKEND_URL}/api/meetings/${meetingId}`, {
                method: 'DELETE',
              });

              if (response.ok) {
                // Remove from local state
                setMeetings(prevMeetings => 
                  prevMeetings.filter(meeting => meeting.id !== meetingId)
                );
                
                // Update AsyncStorage
                const updatedMeetings = meetings.filter(meeting => meeting.id !== meetingId);
                await AsyncStorage.setItem('meetings', JSON.stringify(updatedMeetings));
                
                showAlert('Success', 'Meeting deleted successfully');
              } else {
                showAlert('Error', 'Failed to delete meeting');
              }
            } catch (error) {
              console.error('Error deleting meeting:', error);
              showAlert('Error', 'Failed to delete meeting');
            }
          },
        },
      ]
    );
  };

  const renderDeleteAction = (meetingId: string, meetingTitle: string) => {
    return (
      <View style={styles.deleteAction}>
        <TouchableOpacity
          style={styles.deleteButton}
          onPress={() => deleteMeeting(meetingId, meetingTitle)}
        >
          <Ionicons name="trash" size={24} color="#FFFFFF" />
          <Text style={styles.deleteButtonText}>Delete</Text>
        </TouchableOpacity>
      </View>
    );
  };

  const renderMeeting = ({ item }: { item: Meeting }) => (
    <Swipeable renderRightActions={() => renderDeleteAction(item.id, item.title)}>
      <TouchableOpacity
        style={styles.meetingItem}
        onPress={() => {
          if (item.status === 'completed') {
            router.push(`/meeting/${item.id}`);
          } else if (item.status === 'processing') {
            showAlert('Processing', 'This meeting is still being processed. Please wait...');
          } else {
            showAlert('Not Ready', 'This meeting hasn\'t been processed yet.');
          }
        }}
      >
        <View style={styles.meetingHeader}>
          <Text style={styles.meetingTitle}>{item.title}</Text>
          <View style={[styles.statusBadge, { backgroundColor: getStatusColor(item.status) }]}>
            <Text style={styles.statusText}>{item.status}</Text>
          </View>
        </View>
        
        {item.company_name && (
          <Text style={styles.companyName}>{item.company_name}</Text>
        )}
        
        <Text style={styles.meetingDate}>
          {item.meeting_date 
            ? new Date(item.meeting_date).toLocaleDateString()
            : new Date(item.created_at).toLocaleDateString()
          }
        </Text>
        {item.status === 'processing' && (
          <View style={styles.processingIndicator}>
            <ActivityIndicator size="small" color="#007AFF" />
            <Text style={styles.processingText}>Processing...</Text>
          </View>
        )}
        {item.status === 'completed' && (
          <View style={styles.completedIndicator}>
            <Ionicons name="chevron-forward" size={16} color="#8E8E93" />
            <Text style={styles.tapToViewText}>Tap to view & ask questions</Text>
          </View>
        )}
      </TouchableOpacity>
    </Swipeable>
  );

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

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <StatusBar barStyle="light-content" backgroundColor="#000000" />

      {/* Recording Mode - Focused Interface */}
      {isRecording ? (
        <View style={styles.recordingModeContainer}>
          {/* Recording Status */}
          <View style={styles.recordingStatusContainer}>
            <View style={[styles.recordingIndicator, isPaused && styles.pausedIndicator]} />
            <Text style={styles.recordingStatusText}>
              {isPaused ? 'Recording Paused' : 'Recording in Progress'}
            </Text>
            <Text style={styles.recordingDuration}>
              {formatDuration(recordingDuration)}
            </Text>
          </View>

          {/* Main Recording Button */}
          <TouchableOpacity
            style={[
              styles.recordButton,
              styles.recordingButton,
              isPaused && styles.pausedButton,
            ]}
            onPress={stopRecording}
            disabled={isProcessing}
          >
            {isProcessing ? (
              <ActivityIndicator size="large" color="#FFFFFF" />
            ) : (
              <Ionicons name="stop" size={48} color="#FFFFFF" />
            )}
          </TouchableOpacity>

          {/* Control Buttons */}
          <View style={styles.recordingControls}>
            <TouchableOpacity
              style={[styles.controlButton, isPaused && styles.resumeButton]}
              onPress={isPaused ? resumeRecording : pauseRecording}
              disabled={isProcessing}
            >
              <Ionicons 
                name={isPaused ? 'play' : 'pause'} 
                size={24} 
                color="#FFFFFF" 
              />
              <Text style={styles.controlButtonText}>
                {isPaused ? 'Resume' : 'Pause'}
              </Text>
            </TouchableOpacity>
          </View>

          <Text style={styles.recordingText}>
            {isProcessing
              ? 'Processing recording...'
              : 'Tap stop when finished, or pause to skip sections'}
          </Text>
        </View>
      ) : (
        /* Normal Mode - Show meetings list */
        <>
          <View style={styles.header}>
            <Text style={styles.headerTitle}>Meeting Summarizer</Text>
          </View>

          <View style={styles.recordingSection}>
            <TouchableOpacity
              style={[
                styles.recordButton,
                isProcessing && styles.processingButton,
              ]}
              onPress={startRecording}
              disabled={isProcessing}
            >
              {isProcessing ? (
                <ActivityIndicator size="large" color="#FFFFFF" />
              ) : (
                <Ionicons name="mic" size={48} color="#FFFFFF" />
              )}
            </TouchableOpacity>
            
            <Text style={styles.recordingText}>
              {isProcessing
                ? 'Processing...'
                : 'Tap to start recording'}
            </Text>
          </View>

          <View style={styles.meetingsSection}>
            <Text style={styles.sectionTitle}>Recent Meetings</Text>
            <FlatList
              data={meetings}
              renderItem={renderMeeting}
              keyExtractor={(item) => item.id}
              refreshing={false}
              onRefresh={loadMeetings}
              showsVerticalScrollIndicator={false}
              ListEmptyComponent={
                <Text style={styles.emptyText}>No meetings yet. Start recording!</Text>
              }
            />
          </View>
        </>
      )}

      {/* Custom Alert Modal */}
      {alertConfig && (
        <CustomAlert
          visible={visible}
          title={alertConfig.title}
          message={alertConfig.message}
          buttons={alertConfig.buttons}
          onClose={hideAlert}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000000',
  },
  header: {
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#333333',
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
    textAlign: 'center',
  },
  recordingSection: {
    alignItems: 'center',
    paddingVertical: 40,
  },
  recordButton: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
    ...Platform.select({
      ios: {
        shadowColor: '#007AFF',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.3,
        shadowRadius: 8,
      },
      android: {
        elevation: 8,
      },
    }),
  },
  recordingButton: {
    backgroundColor: '#FF3B30',
    ...Platform.select({
      ios: {
        shadowColor: '#FF3B30',
      },
    }),
  },
  processingButton: {
    backgroundColor: '#FF9500',
    ...Platform.select({
      ios: {
        shadowColor: '#FF9500',
      },
    }),
  },
  recordingText: {
    fontSize: 16,
    color: '#8E8E93',
    textAlign: 'center',
  },
  meetingsSection: {
    flex: 1,
    paddingHorizontal: 20,
    paddingTop: 20,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 16,
  },
  meetingItem: {
    backgroundColor: '#1C1C1E',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  meetingHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  meetingTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    flex: 1,
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
  meetingDate: {
    fontSize: 14,
    color: '#8E8E93',
  },
  companyName: {
    fontSize: 14,
    color: '#007AFF',
    fontWeight: '500',
    marginTop: 4,
  },
  processingIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 8,
  },
  processingText: {
    fontSize: 14,
    color: '#FF9500',
    marginLeft: 8,
  },
  completedIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 8,
  },
  tapToViewText: {
    fontSize: 14,
    color: '#8E8E93',
    marginLeft: 4,
  },
  emptyText: {
    fontSize: 16,
    color: '#8E8E93',
    textAlign: 'center',
    marginTop: 40,
  },
  deleteAction: {
    backgroundColor: '#FF3B30',
    justifyContent: 'center',
    alignItems: 'center',
    width: 80,
    height: '100%',
  },
  deleteButton: {
    justifyContent: 'center',
    alignItems: 'center',
    height: '100%',
    width: '100%',
  },
  deleteButtonText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '600',
    marginTop: 4,
  },
  // Recording Mode Styles
  recordingModeContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 32,
  },
  recordingStatusContainer: {
    alignItems: 'center',
    marginBottom: 60,
  },
  recordingIndicator: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: '#FF3B30',
    marginBottom: 16,
    shadowColor: '#FF3B30',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.6,
    shadowRadius: 4,
    elevation: 4,
  },
  pausedIndicator: {
    backgroundColor: '#FF9500',
    shadowColor: '#FF9500',
  },
  recordingStatusText: {
    fontSize: 24,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 8,
    textAlign: 'center',
  },
  recordingDuration: {
    fontSize: 48,
    fontWeight: '300',
    color: '#FFFFFF',
    fontFamily: Platform.OS === 'ios' ? 'SF Mono' : 'monospace',
  },
  pausedButton: {
    backgroundColor: '#FF9500',
    ...Platform.select({
      ios: {
        shadowColor: '#FF9500',
      },
    }),
  },
  recordingControls: {
    flexDirection: 'row',
    marginTop: 40,
    gap: 20,
  },
  controlButton: {
    backgroundColor: '#1C1C1E',
    paddingHorizontal: 24,
    paddingVertical: 16,
    borderRadius: 25,
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 100,
    borderWidth: 1,
    borderColor: '#333333',
  },
  resumeButton: {
    backgroundColor: '#34C759',
    borderColor: '#34C759',
  },
  controlButtonText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '500',
    marginTop: 4,
  },
});