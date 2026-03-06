import { api } from 'src/boot/axios';

export type ChatMessage = {
  id: number;
  sender_username: string;
  content: string;
  created_at: string;
};

export async function listMessages(): Promise<ChatMessage[]> {
  const { data } = await api.get<{ results: ChatMessage[] }>('/chat/messages/');
  return data.results;
}

export async function sendMessage(content: string): Promise<ChatMessage> {
  const { data } = await api.post<ChatMessage>('/chat/messages/send/', { content });
  return data;
}
