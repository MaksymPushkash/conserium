export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
export const API_V1_URL = `${API_BASE_URL}/api/v1`;
export const DEV_TOOLS_ENABLED = process.env.NEXT_PUBLIC_DEV_TOOLS !== "false";
