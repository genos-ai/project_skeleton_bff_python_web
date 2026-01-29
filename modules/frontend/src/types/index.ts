/**
 * Shared TypeScript types.
 *
 * Add shared type definitions here.
 */

// API Response types
export interface ApiResponse<T> {
  success: boolean
  data: T | null
  error: ApiError | null
  metadata: ResponseMetadata
}

export interface ApiError {
  code: string
  message: string
  details?: Record<string, unknown>
}

export interface ResponseMetadata {
  timestamp: string
  request_id: string | null
}

// Pagination types
export interface PaginationInfo {
  total?: number
  limit: number
  cursor?: string
  next_cursor?: string
  has_more: boolean
}

export interface PaginatedResponse<T> {
  success: boolean
  data: T[]
  error: null
  metadata: ResponseMetadata
  pagination: PaginationInfo
}

// Add domain-specific types below
