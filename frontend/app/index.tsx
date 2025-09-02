import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  Alert,
  SafeAreaView,
  StatusBar,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { Audio } from 'expo-audio';
import * as FileSystem from 'expo-file-system';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';

interface Meeting {
  id: string;
  title: string;
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
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [hasPermission, setHasPermission] = useState(false);

  const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

  useEffect(() => {
    requestPermissions();
    loadMeetings();
  }, []);

  const requestPermissions = async () => {
    try {
      const { status } = await Audio.requestPermissionsAsync();
      setHasPermission(status === 'granted');
      
      if (status !== 'granted') {
        Alert.alert(
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
      const { recording: newRecording } = await Audio.createRecordingAsync(
        Audio.RecordingOptions.HIGH_QUALITY
      );

      setRecording(newRecording);
      setIsRecording(true);
    } catch (error) {
      console.error('Failed to start recording', error);
      Alert.alert('Error', 'Failed to start recording');
    }
  };

  const stopRecording = async () => {
    if (!recording) return;

    try {
      setIsRecording(false);
      await recording.stopAsync();
      const uri = recording.getURI();
      
      if (uri) {
        await processRecording(uri);
      }
      
      setRecording(null);
    } catch (error) {
      console.error('Failed to stop recording', error);
      Alert.alert('Error', 'Failed to stop recording');
    }
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

      Alert.alert(
        'Processing Started',
        'Your meeting is being processed. This may take a few minutes.',
        [{ text: 'OK' }]
      );

      // Poll for completion
      pollMeetingStatus(meeting.id);
      
    } catch (error) {
      console.error('Error processing recording:', error);
      Alert.alert('Error', 'Failed to process recording');
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
            Alert.alert(
              'Processing Complete',
              'Your meeting has been transcribed and summarized!',
              [{ text: 'OK' }]
            );
            return;
          } else if (meeting.status === 'error') {
            Alert.alert('Error', 'Failed to process meeting');
            return;
          }
        }

        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 10000); // Poll every 10 seconds
        } else {
          Alert.alert('Timeout', 'Processing is taking longer than expected');
        }
      } catch (error) {
        console.error('Error polling status:', error);
      }
    };

    poll();
  };

  const renderMeeting = ({ item }: { item: Meeting }) => (
    <TouchableOpacity
      style={styles.meetingItem}
      onPress={() => {
        if (item.status === 'completed') {
          // Navigate to meeting details (you can implement this)
          Alert.alert(
            item.title,
            `Summary: ${item.summary}\n\nKey Points: ${item.key_points?.join(', ')}\n\nAction Items: ${item.action_items?.join(', ')}`,
            [{ text: 'OK' }]
          );
        }
      }}
    >
      <View style={styles.meetingHeader}>
        <Text style={styles.meetingTitle}>{item.title}</Text>
        <View style={[styles.statusBadge, { backgroundColor: getStatusColor(item.status) }]}>
          <Text style={styles.statusText}>{item.status}</Text>
        </View>
      </View>
      <Text style={styles.meetingDate}>
        {new Date(item.created_at).toLocaleDateString()}
      </Text>
      {item.status === 'processing' && (
        <View style={styles.processingIndicator}>
          <ActivityIndicator size="small" color="#007AFF" />
          <Text style={styles.processingText}>Processing...</Text>
        </View>
      )}
    </TouchableOpacity>
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
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" />
      
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Meeting Summarizer</Text>
      </View>

      <View style={styles.recordingSection}>
        <TouchableOpacity
          style={[
            styles.recordButton,
            isRecording && styles.recordingButton,
            isProcessing && styles.processingButton,
          ]}
          onPress={isRecording ? stopRecording : startRecording}
          disabled={isProcessing}
        >
          {isProcessing ? (
            <ActivityIndicator size="large" color="#FFFFFF" />
          ) : (
            <Ionicons
              name={isRecording ? 'stop' : 'mic'}
              size={48}
              color="#FFFFFF"
            />
          )}
        </TouchableOpacity>
        
        <Text style={styles.recordingText}>
          {isProcessing
            ? 'Processing...'
            : isRecording
            ? 'Tap to stop recording'
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
    </SafeAreaView>
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
    shadowColor: '#007AFF',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  recordingButton: {
    backgroundColor: '#FF3B30',
    shadowColor: '#FF3B30',
  },
  processingButton: {
    backgroundColor: '#FF9500',
    shadowColor: '#FF9500',
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
  emptyText: {
    fontSize: 16,
    color: '#8E8E93',
    textAlign: 'center',
    marginTop: 40,
  },
});