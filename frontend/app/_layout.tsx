import { Stack } from 'expo-router';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <Stack>
        <Stack.Screen 
          name="index" 
          options={{ 
            headerShown: false,
            title: 'Meeting Summarizer'
          }} 
        />
        <Stack.Screen 
          name="meeting/[id]" 
          options={{ 
            headerShown: false,
            title: 'Meeting Details'
          }} 
        />
      </Stack>
    </GestureHandlerRootView>
  );
}