// Simple fetch-based API client (no axios dependency)
const API_BASE_URL = 'http://localhost:8000';

const chatApi = {
  sendMessage: async (data) => {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: data.message,
          conversation_id: data.conversation_id || null,
          thread_id: data.thread_id || null,
          context: data.context || null,
          wait_for_feedback: data.wait_for_feedback || false
        })
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('Error sending message:', error);
      throw error;
    }
  },

  fetchConversation: async (conversationId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/conversation/${conversationId}`);
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('Error fetching conversation:', error);
      throw error;
    }
  },

  fetchConversationsByThread: async (threadId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/thread/${threadId}/conversations`);
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      const data = await response.json();
      
      // Process the conversations to match the expected format in the frontend
      if (data.status === 'success' && Array.isArray(data.conversations)) {
        // Group user and assistant messages
        const processedConversations = [];
        let currentQuestion = null;
        
        data.conversations.forEach(conv => {
          if (conv.role === 'user') {
            // Save the question
            currentQuestion = {
              conversation_id: conv.conversation_id,
              thread_id: conv.thread_id,
              question: conv.content,
              answer: '',
              timestamp: conv.timestamp,
              metadata: {}
            };
            processedConversations.push(currentQuestion);
          } else if (conv.role === 'assistant' && currentQuestion) {
            // Add the answer to the current question
            currentQuestion.answer = conv.content;
          }
        });
        
        return {
          status: 'success',
          conversations: processedConversations
        };
      }
      
      return data;
    } catch (error) {
      console.error('Error fetching thread conversations:', error);
      throw error;
    }
  },

  submitFeedback: async (feedback) => {
    try {
      const response = await fetch(`${API_BASE_URL}/feedback/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(feedback)
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('Error submitting feedback:', error);
      throw error;
    }
  },

  fetchRecentConversations: async () => {
    try {
      // Log the full URL to debug connection issues
      const url = `${API_BASE_URL}/api/thread-conversations`;
      console.log("⭐ Attempting to fetch conversations from:", url);
      console.log("⭐ API_BASE_URL value:", API_BASE_URL);
      
      // Use our new thread conversations endpoint
      const response = await fetch(url);
      
      console.log("Response status:", response.status, response.statusText);
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status} - ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log("Response data:", data);
      
      return data;
    } catch (error) {
      console.error('❌ Error fetching recent conversations:', error);
      throw error;
    }
  },

  clearConversation: async (conversationId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/conversation/${conversationId}/clear`, {
        method: 'POST'
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('Error clearing conversation:', error);
      throw error;
    }
  },

  analyzeWithArchitect: async (data) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/architect/analyze/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: data.query,
          conversation_id: data.conversation_id || null,
          thread_id: data.thread_id || null,
          provider: data.provider || null,
          model: data.model || null
        })
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('Error sending query to architect:', error);
      throw error;
    }
  }
};

export default chatApi; 