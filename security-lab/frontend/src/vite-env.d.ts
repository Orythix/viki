/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_LAB_API_KEY: string;
  readonly VITE_LAB_ROLE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
