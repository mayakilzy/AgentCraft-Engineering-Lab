/**
 * i18n setup with i18next + react-i18next.
 * Two locales: English (default, LTR) and Arabic (RTL).
 * Technical symbols (codes, labels) are NOT translated per A12.
 */
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import ar from './locales/ar.json';

export type Locale = 'en' | 'ar';
export const SUPPORTED_LOCALES: Locale[] = ['en', 'ar'];
export const DEFAULT_LOCALE: Locale = 'en';

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    ar: { translation: ar },
  },
  lng: DEFAULT_LOCALE,
  fallbackLng: DEFAULT_LOCALE,
  interpolation: { escapeValue: false },
  returnNull: false,
});

export function applyDocumentDir(locale: Locale): void {
  if (typeof document === 'undefined') return;
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr';
}

export function pickLocale(value: string | null | undefined): Locale {
  return value === 'ar' ? 'ar' : 'en';
}

export default i18n;
