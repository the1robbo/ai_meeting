import React, { createContext, useContext, useState, useEffect } from 'react';
import { useColorScheme } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

export type ThemeMode = 'light' | 'dark' | 'system';

export interface Theme {
  colors: {
    background: string;
    surface: string;
    primary: string;
    secondary: string;
    accent: string;
    text: string;
    textSecondary: string;
    textTertiary: string;
    border: string;
    card: string;
    success: string;
    warning: string;
    error: string;
    progressBar: string;
    statusBar: 'light-content' | 'dark-content';
  };
}

export const lightTheme: Theme = {
  colors: {
    background: '#FFFFFF',
    surface: '#F2F2F7',
    primary: '#007AFF',
    secondary: '#5856D6',
    accent: '#007AFF',
    text: '#000000',
    textSecondary: '#3C3C43',
    textTertiary: '#8E8E93',
    border: '#C6C6C8',
    card: '#FFFFFF',
    success: '#34C759',
    warning: '#FF9500',
    error: '#FF3B30',
    progressBar: '#007AFF',
    statusBar: 'dark-content',
  },
};

export const darkTheme: Theme = {
  colors: {
    background: '#000000',
    surface: '#1C1C1E',
    primary: '#007AFF',
    secondary: '#5856D6',
    accent: '#007AFF',
    text: '#FFFFFF',
    textSecondary: '#E5E5E7',
    textTertiary: '#8E8E93',
    border: '#333333',
    card: '#1C1C1E',
    success: '#34C759',
    warning: '#FF9500',
    error: '#FF3B30',
    progressBar: '#007AFF',
    statusBar: 'light-content',
  },
};

interface ThemeContextType {
  theme: Theme;
  themeMode: ThemeMode;
  setThemeMode: (mode: ThemeMode) => void;
  isDark: boolean;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const systemColorScheme = useColorScheme();
  const [themeMode, setThemeModeState] = useState<ThemeMode>('system');

  // Determine current theme based on mode
  const getTheme = (mode: ThemeMode): Theme => {
    if (mode === 'system') {
      return systemColorScheme === 'dark' ? darkTheme : lightTheme;
    }
    return mode === 'dark' ? darkTheme : lightTheme;
  };

  const [theme, setTheme] = useState<Theme>(getTheme(themeMode));
  const isDark = theme === darkTheme;

  // Load saved theme preference
  useEffect(() => {
    const loadThemePreference = async () => {
      try {
        const savedTheme = await AsyncStorage.getItem('themeMode');
        if (savedTheme && ['light', 'dark', 'system'].includes(savedTheme)) {
          const mode = savedTheme as ThemeMode;
          setThemeModeState(mode);
          setTheme(getTheme(mode));
        }
      } catch (error) {
        console.error('Error loading theme preference:', error);
      }
    };

    loadThemePreference();
  }, []);

  // Update theme when system color scheme changes (for system mode)
  useEffect(() => {
    if (themeMode === 'system') {
      setTheme(getTheme('system'));
    }
  }, [systemColorScheme, themeMode]);

  // Set theme mode and save to storage
  const setThemeMode = async (mode: ThemeMode) => {
    try {
      setThemeModeState(mode);
      setTheme(getTheme(mode));
      await AsyncStorage.setItem('themeMode', mode);
    } catch (error) {
      console.error('Error saving theme preference:', error);
    }
  };

  return (
    <ThemeContext.Provider value={{ theme, themeMode, setThemeMode, isDark }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}