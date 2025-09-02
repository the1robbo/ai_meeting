import { Stack } from 'expo-router';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { ThemeProvider } from '../contexts/ThemeContext';

export default function RootLayout() {
  return (
    <ThemeProvider>
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
    </ThemeProvider>
  );
}