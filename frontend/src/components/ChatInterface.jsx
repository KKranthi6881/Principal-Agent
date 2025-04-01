import React, { useState, useEffect } from 'react';
import { v4 as uuidv4 } from 'uuid';
import ReactMarkdown from 'react-markdown';
import '../assets/ChatInterface.css';

const ChatInterface = ({ 
  messages = [],
  setMessages,
  currentConversationId,
  setCurrentConversationId,
  currentThreadId,
  setCurrentThreadId,
  fetchConversations,
  formatTimestamp,
  isLoading,
  setIsLoading,
  error,
  setError
}) => {
  const [feedbackRequired, setFeedbackRequired] = useState(false);
  const [currentFeedbackId, setCurrentFeedbackId] = useState(null);
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
  const [feedbackError, setFeedbackError] = useState(null);

  // Update the handleMessageSubmit function to handle the feedback interface
  const handleMessageSubmit = async (message) => {
    try {
      setIsLoading(true);
      setError(null);
      
      // Add user message to chat
      const userMessage = {
        id: uuidv4(),
        role: 'user',
        content: message,
        timestamp: new Date().toISOString()
      };
      
      setMessages(prevMessages => [...prevMessages, userMessage]);
      
      // Send message to backend
      const response = await fetch('/chat/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: message,
          conversation_id: currentConversationId,
          thread_id: currentThreadId,
          wait_for_feedback: false
        }),
      });
      
      const data = await response.json();
      
      if (response.ok) {
        // Update conversation ID and thread ID
        setCurrentConversationId(data.conversation_id);
        setCurrentThreadId(data.thread_id || currentThreadId);
        
        // Add assistant message to chat
        const assistantMessage = {
          id: uuidv4(),
          role: 'assistant',
          content: data.answer,
          timestamp: new Date().toISOString(),
          feedback_id: data.feedback_id,
          parsed_question: data.parsed_question,
          feedback_required: data.feedback_required,
          feedback_status: data.feedback_status
        };
        
        setMessages(prevMessages => [...prevMessages, assistantMessage]);
        
        // Check if feedback is required
        if (data.feedback_required && data.feedback_id) {
          setFeedbackRequired(true);
          setCurrentFeedbackId(data.feedback_id);
          console.log("Feedback required for ID:", data.feedback_id);
        }
        
        // Fetch updated conversations
        fetchConversations();
      } else {
        setError(data.error || 'Failed to send message');
      }
    } catch (error) {
      console.error('Error sending message:', error);
      setError('Failed to send message. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  // Add a FeedbackComponent to display the feedback interface
  const FeedbackComponent = ({ feedbackId, onSubmit }) => {
    const [approved, setApproved] = useState(true);
    const [comments, setComments] = useState('');
    
    const handleSubmit = (e) => {
      e.preventDefault();
      onSubmit(feedbackId, approved, comments);
    };
    
    return (
      <div className="feedback-container">
        <h3>Please review this analysis</h3>
        <form onSubmit={handleSubmit}>
          <div className="feedback-options">
            <label>
              <input
                type="radio"
                name="feedback"
                checked={approved}
                onChange={() => setApproved(true)}
              />
              Approve
            </label>
            <label>
              <input
                type="radio"
                name="feedback"
                checked={!approved}
                onChange={() => setApproved(false)}
              />
              Needs Improvement
            </label>
          </div>
          
          {!approved && (
            <textarea
              placeholder="Please provide feedback on what needs improvement..."
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              rows={3}
            />
          )}
          
          <button type="submit" className="submit-button">
            Submit Feedback
          </button>
        </form>
      </div>
    );
  };

  // Add this to the component to log messages for debugging
  useEffect(() => {
    console.log("Current messages:", messages);
    console.log("Feedback required:", feedbackRequired);
    console.log("Current feedback ID:", currentFeedbackId);
  }, [messages, feedbackRequired, currentFeedbackId]);

  // Add a new component to format the architect's response
  const ArchitectResponse = ({ content, technical_details }) => {
    // Extract sections from the content
    const formatContent = () => {
      // If there are no sections, just return the content as is
      if (!technical_details || !technical_details.sections || Object.keys(technical_details.sections).length === 0) {
        return <ReactMarkdown>{content}</ReactMarkdown>;
      }
      
      // Otherwise, format the content with collapsible sections
      return (
        <div className="architect-response">
          <h3>Data Architect Solution</h3>
          
          {/* Extract and display sections */}
          {content.split('##').map((section, index) => {
            if (index === 0) return null; // Skip the first split which is empty
            
            const sectionLines = section.trim().split('\n');
            const sectionTitle = sectionLines[0].trim();
            const sectionContent = sectionLines.slice(1).join('\n').trim();
            
            return (
              <details key={index} open={index === 1}>
                <summary className="section-header">{sectionTitle}</summary>
                <div className="section-content">
                  <ReactMarkdown>{sectionContent}</ReactMarkdown>
                </div>
              </details>
            );
          })}
          
          {/* Add collapsible technical details */}
          <details className="technical-details">
            <summary>Technical Details</summary>
            <div className="details-content">
              {technical_details.schema_results && technical_details.schema_results.length > 0 && (
                <div className="schema-results">
                  <h4>Schema Results</h4>
                  {technical_details.schema_results.map((schema, idx) => (
                    <div key={idx} className="schema-item">
                      <h5>{schema.schema_name}.{schema.table_name}</h5>
                      <p><strong>Columns:</strong> {Array.isArray(schema.columns) ? schema.columns.join(', ') : schema.columns}</p>
                      <p><strong>Relevance:</strong> {(schema.relevance_score * 10).toFixed(1)}/10</p>
                      {schema.explanation && <p><strong>Explanation:</strong> {schema.explanation}</p>}
                    </div>
                  ))}
                </div>
              )}
              
              {technical_details.code_results && technical_details.code_results.length > 0 && (
                <div className="code-results">
                  <h4>Code Examples</h4>
                  {technical_details.code_results.map((code, idx) => (
                    <div key={idx} className="code-item">
                      <h5>{code.file_path}</h5>
                      <p><strong>Relevance:</strong> {(code.relevance_score * 10).toFixed(1)}/10</p>
                      {code.explanation && <p><strong>Explanation:</strong> {code.explanation}</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </details>
        </div>
      );
    };
    
    return (
      <div className="formatted-response">
        {formatContent()}
      </div>
    );
  };

  // Update the handleFeedbackSubmit function to handle architect response
  const handleFeedbackSubmit = async (feedbackId, approved, comments) => {
    try {
      setIsSubmittingFeedback(true);
      setFeedbackError(null); // Clear any previous errors
      
      // Send feedback to backend
      const response = await fetch('/feedback/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          feedback_id: feedbackId,
          approved: approved,
          comments: comments
        }),
      });
      
      const data = await response.json();
      
      if (response.ok) {
        // Update message with feedback status
        setMessages(prevMessages =>
          prevMessages.map(msg =>
            msg.feedback_id === feedbackId
              ? { ...msg, feedback_status: 'submitted' }
              : msg
          )
        );
        
        setFeedbackRequired(false);
        setCurrentFeedbackId(null);
        
        console.log('Feedback submitted successfully:', data);
        
        // If the response contains an updated answer, update the message
        if (data.updated_answer) {
          setMessages(prevMessages => {
            // Find the index of the message with the feedback_id
            const msgIndex = prevMessages.findIndex(msg => msg.feedback_id === feedbackId);
            
            if (msgIndex !== -1) {
              // Create a new array with the updated message
              const updatedMessages = [...prevMessages];
              updatedMessages[msgIndex] = {
                ...updatedMessages[msgIndex],
                content: data.updated_answer,
                technical_details: data.technical_details || {},
                feedback_status: 'updated'
              };
              
              return updatedMessages;
            }
            
            return prevMessages;
          });
        }
      } else {
        setFeedbackError(data.error || 'Failed to submit feedback');
        console.error('Feedback submission error:', data.error);
      }
    } catch (error) {
      console.error('Error submitting feedback:', error);
      setFeedbackError('Failed to submit feedback. Please try again.');
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  // Add a debug panel component to display debug information
  const DebugPanel = ({ messages, feedbackRequired, currentFeedbackId }) => {
    return (
      <div className="debug-panel">
        <h3>Debug Information</h3>
        <p><strong>Messages:</strong> {messages.length}</p>
        <p><strong>Feedback Required:</strong> {String(feedbackRequired)}</p>
        <p><strong>Current Feedback ID:</strong> {currentFeedbackId || 'none'}</p>
        
        <h4>Message Details:</h4>
        {messages.map((msg, idx) => (
          <div key={idx} className="debug-message">
            <p><strong>Index:</strong> {idx}</p>
            <p><strong>Role:</strong> {msg.role}</p>
            <p><strong>ID:</strong> {msg.id}</p>
            <p><strong>Feedback ID:</strong> {msg.feedback_id || 'none'}</p>
            <p><strong>Feedback Required:</strong> {String(!!msg.feedback_required)}</p>
            <p><strong>Feedback Status:</strong> {msg.feedback_status || 'none'}</p>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="chat-interface">
      <div className="messages-container">
        {messages.map((message, index) => {
          console.log(`Rendering message ${index}:`, message);
          return (
            <div key={message.id} className={`message ${message.role}`}>
              <div className="message-content">
                {message.technical_details && Object.keys(message.technical_details).length > 0 ? (
                  <ArchitectResponse 
                    content={message.content} 
                    technical_details={message.technical_details} 
                  />
                ) : (
                  <ReactMarkdown>{message.content}</ReactMarkdown>
                )}
                
                {message.role === 'assistant' && (
                  <div className="message-debug" style={{fontSize: '10px', color: '#888', display: 'none'}}>
                    feedback_id: {message.feedback_id || 'none'}<br/>
                    feedback_required: {String(message.feedback_required)}<br/>
                    feedback_status: {message.feedback_status || 'none'}
                  </div>
                )}
                
                {message.role === 'assistant' && 
                message.feedback_required && 
                message.feedback_id && 
                message.feedback_status === 'pending' && (
                  <FeedbackComponent
                    feedbackId={message.feedback_id}
                    onSubmit={handleFeedbackSubmit}
                  />
                )}
              </div>
              <div className="message-timestamp">
                {formatTimestamp(message.timestamp)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ChatInterface; 