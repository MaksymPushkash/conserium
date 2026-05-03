export type DocumentType = "PDF" | "URL" | "YOUTUBE" | "AUDIO" | "IMAGE" | "TEXT" | "MARKDOWN";
export type DocumentStatus = "PENDING" | "QUEUED" | "PROCESSING" | "READY" | "FAILED";

export type MetadataItem = Record<string, unknown>;

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
}

export interface UserResponse {
  id: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface DocumentResponse {
  id: string;
  user_id: string;
  collection_id: string | null;
  title: string;
  type: DocumentType;
  status: DocumentStatus;
  source_url: string | null;
  file_path: string | null;
  file_size_bytes: number | null;
  raw_content: string | null;
  summary: string | null;
  word_count: number | null;
  language: string | null;
  entities: MetadataItem[] | null;
  categories: MetadataItem[] | null;
  visual_metadata: MetadataItem | null;
  tags: string[];
  is_duplicate: boolean;
  duplicate_of_id: string | null;
  created_at: string;
  updated_at: string | null;
}

export type DocumentListItem = Omit<DocumentResponse, "raw_content" | "entities" | "categories" | "visual_metadata">;

export interface DocumentListResponse {
  items: DocumentListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface DocumentStatusResponse {
  document_id: string;
  status: DocumentStatus | string;
  progress: number;
  message: string;
}

export interface ChatSession {
  id: string;
  user_id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface ChatListResponse {
  items: ChatSession[];
  total: number;
  limit: number;
  offset: number;
}

export interface ChatMessageResponse {
  id: string;
  chat_id: string;
  role: "user" | "assistant" | "system" | string;
  content: string;
  sources: QuerySource[] | null;
  refrag_context: RefragContext | null;
  eval_scores: Record<string, unknown> | null;
  trace_id: string | null;
  created_at: string;
}

export interface ChatDetailResponse {
  session: ChatSession;
  messages: ChatMessageResponse[];
}

export interface Note {
  id: string;
  title: string;
  content: string;
  status: DocumentStatus;
  word_count: number;
  language: string | null;
  created_at: string;
  updated_at: string | null;
}

export type NoteListItem = Omit<Note, "content">;

export interface NoteListResponse {
  items: NoteListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface IngestDocumentPayload {
  title: string;
  type: DocumentType;
  collection_id?: string | null;
  source_url?: string | null;
  raw_content?: string | null;
  language?: string | null;
}

export interface QueryRequest {
  query: string;
  conversation_id?: string | null;
  collection_id?: string | null;
  document_types?: DocumentType[] | null;
  limit: number;
}

export interface QuerySource {
  chunk_id: string;
  document_id: string;
  document_title: string | null;
  content: string;
  page_number: number | null;
  chunk_index: number;
  score: number | null;
  citation?: string;
}

export interface RefragChunk {
  chunk_id: string;
  document_id: string;
  document_title: string | null;
  representation: "FULL_TEXT" | "COMPRESSED" | "DISCARDED";
  page_number: number | null;
  chunk_index: number;
  score: number | null;
  context_text: string;
  original_token_count: number;
  context_token_count: number;
  citation: string | null;
}

export interface RefragContext {
  full_text_chunks: RefragChunk[];
  compressed_chunks: RefragChunk[];
  discarded_chunks: RefragChunk[];
  total_original_tokens: number;
  total_context_tokens: number;
  compression_strategy: string;
}

export interface QueryResponse {
  conversation_id: string;
  query: string;
  answer: string;
  sources: QuerySource[];
  refrag_context: RefragContext;
}

export type QueryStreamEventName = "metadata" | "token" | "sources" | "refrag_context" | "done" | "error";

export interface QueryStreamEvent {
  event: QueryStreamEventName;
  data: Record<string, unknown>;
}
