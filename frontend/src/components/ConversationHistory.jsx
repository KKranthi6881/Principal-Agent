import React, { useState, useEffect, Fragment } from 'react';
import { Link } from 'react-router-dom';
import { 
  Box, 
  VStack,
  Text,
  Heading,
  Card,
  CardBody,
  Badge,
  Flex,
  Button,
  Accordion,
  AccordionItem,
  AccordionButton,
  AccordionPanel,
  AccordionIcon,
  Divider,
  useToast
} from '@chakra-ui/react';
import { IoAdd, IoTrash } from 'react-icons/io5';
import { fetchRecentConversations, fetchConversationsByThread, clearConversation } from '../api/chatApi';

const API_BASE_URL = 'http://localhost:8000'; // Replace with your actual API base URL

const ConversationHistory = ({ onSelectConversation, onNewChat }) => {
  const [threads, setThreads] = useState([]);
  const [expandedThreads, setExpandedThreads] = useState({});
  const [threadConversations, setThreadConversations] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const toast = useToast();

  useEffect(() => {
    // Check database connection first, then load conversations
    checkDatabaseConnection();
  }, []);

  const checkDatabaseConnection = async () => {
    try {
      console.log("Checking database connection...");
      
      // Try direct fetch to check network connectivity first
      const testUrl = `${API_BASE_URL}/health`;
      console.log("Testing basic connectivity with:", testUrl);
      
      try {
        const basicTest = await fetch(testUrl);
        console.log("Basic connectivity test result:", basicTest.status, basicTest.statusText);
      } catch (connErr) {
        console.error("❌ CRITICAL: Basic connectivity failed:", connErr);
        setError(`Cannot connect to backend server at ${API_BASE_URL}. Please check if the server is running.`);
        setLoading(false);
        return;
      }
      
      // Now try the database test
      const dbUrl = `${API_BASE_URL}/api/test-database`;
      console.log("Testing database with:", dbUrl);
      const response = await fetch(dbUrl);
      const data = await response.json();
      console.log("Database check result:", data);
      
      if (data.status === 'success') {
        if (data.row_counts && data.row_counts.threads > 0) {
          console.log(`Found ${data.row_counts.threads} threads in database`);
          loadConversations();
        } else {
          console.warn("No conversation threads found in database");
          setError("No conversation threads found in the database. Try creating a new conversation first.");
          setLoading(false);
        }
      } else {
        console.error("Database check failed:", data.detail);
        setError(`Database check failed: ${data.detail}`);
        setLoading(false);
      }
    } catch (err) {
      console.error("❌ Error checking database:", err);
      setError(`Error checking database: ${err.message}`);
      setLoading(false);
      
      // As a fallback, try loading conversations directly
      console.log("Attempting to load conversations directly as fallback...");
      loadConversations();
    }
  };

  const loadConversations = async () => {
    try {
      setLoading(true);
      console.log("Making API request to fetch conversations...");
      const response = await fetchRecentConversations();
      console.log("API response received:", response);
      
      if (response.status === 'success') {
        // The backend now returns threads
        setThreads(response.threads || []);
        console.log("Loaded threads:", response.threads);
      } else {
        console.error("API returned error status:", response);
        setError("Failed to load conversations: " + (response.detail || "Unknown error"));
      }
    } catch (err) {
      console.error('Error loading conversations:', err);
      setError(err.message);
      toast({
        title: 'Error',
        description: 'Failed to load conversation history',
        status: 'error',
        duration: 3000,
      });
    } finally {
      setLoading(false);
    }
  };

  const toggleThreadExpansion = async (threadId) => {
    // Toggle expansion state
    setExpandedThreads(prev => ({
      ...prev,
      [threadId]: !prev[threadId]
    }));
    
    // If expanding and we don't have conversations for this thread yet, fetch them
    if (!expandedThreads[threadId] && !threadConversations[threadId]) {
      try {
        const response = await fetchConversationsByThread(threadId);
        console.log('Thread conversations response:', response); // Debug log
        
        if (response.status === 'success') {
          setThreadConversations(prev => ({
            ...prev,
            [threadId]: response.conversations || []
          }));
          console.log(`Loaded conversations for thread ${threadId}:`, response.conversations);
        } else {
          console.error(`Error in API response: ${response.detail || "Unknown error"}`);
          toast({
            title: 'Error',
            description: 'Failed to load thread conversations',
            status: 'error',
            duration: 3000,
          });
        }
      } catch (err) {
        console.error(`Error loading conversations for thread ${threadId}:`, err);
        toast({
          title: 'Error',
          description: 'Failed to load thread conversations',
          status: 'error',
          duration: 3000,
        });
      }
    }
  };

  const handleClearConversation = async (conversationId, e) => {
    e.stopPropagation(); // Prevent triggering the parent click event
    
    try {
      await clearConversation(conversationId);
      toast({
        title: 'Conversation cleared',
        status: 'success',
        duration: 2000,
      });
      
      // Refresh the conversation list
      loadConversations();
    } catch (err) {
      console.error('Error clearing conversation:', err);
      toast({
        title: 'Error',
        description: 'Failed to clear conversation',
        status: 'error',
        duration: 3000,
      });
    }
  };

  const renderThreadConversations = (conversations) => {
    return (
      <VStack spacing={2} align="stretch">
        {conversations.map((conv, index) => {
          // Parse technical details if needed
          let architectResponse = conv.architect_response;
          if (!architectResponse && conv.technical_details) {
            try {
              const technicalDetails = JSON.parse(conv.technical_details);
              architectResponse = technicalDetails.architect_response;
            } catch (err) {
              console.error('Error parsing technical details:', err);
            }
          }

          return (
            <Box 
              key={conv.id}
              borderWidth="1px"
              borderRadius="md"
              p={3}
              bg={architectResponse ? "purple.50" : "white"}
            >
              {/* User Query */}
              <Flex direction="column" mb={2}>
                <Text fontSize="sm" fontWeight="medium">
                  <Badge colorScheme="blue" mr={2}>User</Badge>
                  {conv.query}
                </Text>
                <Text fontSize="xs" color="gray.500">
                  {new Date(conv.timestamp).toLocaleString()}
                </Text>
              </Flex>

              {/* Assistant Response */}
              {conv.response && (
                <Flex direction="column" mb={2} pl={4}>
                  <Text fontSize="sm">
                    <Badge colorScheme="green" mr={2}>Assistant</Badge>
                    {conv.response}
                  </Text>
                </Flex>
              )}

              {/* Data Architect Response */}
              {architectResponse && (
                <Flex direction="column" pl={4} mt={2}>
                  <Text fontSize="sm">
                    <Badge colorScheme="purple" mr={2}>Data Architect</Badge>
                    {architectResponse.response}
                  </Text>
                  {architectResponse.sections && (
                    <Accordion allowToggle size="sm" mt={2}>
                      <AccordionItem>
                        <AccordionButton>
                          <Box flex="1" textAlign="left">
                            View Details
                          </Box>
                          <AccordionIcon />
                        </AccordionButton>
                        <AccordionPanel>
                          {Object.entries(architectResponse.sections).map(([key, value]) => (
                            <Box key={key} mb={2}>
                              <Text fontSize="sm" fontWeight="bold" color="purple.600">
                                {key.replace(/_/g, ' ').toUpperCase()}
                              </Text>
                              <Text fontSize="sm" whiteSpace="pre-wrap">{value}</Text>
                            </Box>
                          ))}
                        </AccordionPanel>
                      </AccordionItem>
                    </Accordion>
                  )}
                </Flex>
              )}

              {/* Feedback Status */}
              <Flex justify="space-between" align="center" mt={2}>
                <Badge 
                  colorScheme={
                    conv.feedback_status === 'approved' ? 'green' : 
                    conv.feedback_status === 'pending' ? 'yellow' : 
                    'red'
                  }
                >
                  {conv.feedback_status || 'pending'}
                </Badge>
                <Button
                  size="xs"
                  variant="ghost"
                  colorScheme="red"
                  onClick={(e) => handleClearConversation(conv.id, e)}
                >
                  <IoTrash />
                </Button>
              </Flex>
            </Box>
          );
        })}
      </VStack>
    );
  };

  return (
    <Box p={4}>
      <Flex justify="space-between" align="center" mb={4}>
        <Heading size="md">Conversation History</Heading>
        <Button 
          leftIcon={<IoAdd />} 
          colorScheme="blue" 
          size="sm"
          onClick={onNewChat}
        >
          New Chat
        </Button>
      </Flex>
      
      <Divider mb={4} />
      
      <VStack spacing={3} align="stretch">
        {loading ? (
          <Text textAlign="center">Loading conversations...</Text>
        ) : error ? (
          <Text textAlign="center" color="red.500">{error}</Text>
        ) : threads.length === 0 ? (
          <Text textAlign="center" color="gray.500">No conversations yet</Text>
        ) : (
          threads.map(thread => (
            <Card key={thread.thread_id} variant="outline" mb={2}>
              <CardBody p={3}>
                <Box>
                  <Flex justify="space-between" align="center" mb={2}>
                    <Text fontWeight="bold" fontSize="sm">Thread Started</Text>
                    <Text fontSize="xs" color="gray.500">
                      {new Date(thread.thread_created_at || thread.latest_timestamp).toLocaleString()}
                    </Text>
                  </Flex>
                  
                  <Box 
                    bg="gray.50" 
                    p={2} 
                    borderRadius="md" 
                    mb={2}
                    cursor="pointer"
                    onClick={() => onSelectConversation(thread.first_conversation_id)}
                    _hover={{ bg: "gray.100" }}
                  >
                    <Text fontWeight="medium" noOfLines={2}>
                      {thread.latest_question || thread.topic || "Untitled conversation"}
                    </Text>
                  </Box>

                  {thread.conversation_count > 1 && (
                    <Accordion allowToggle>
                      <AccordionItem border="none">
                        <AccordionButton 
                          p={2} 
                          _hover={{ bg: "gray.50" }}
                          onClick={() => toggleThreadExpansion(thread.thread_id)}
                        >
                          <Box flex="1" textAlign="left" fontSize="sm">
                            <Badge colorScheme="blue" mr={2}>
                              {thread.conversation_count} messages
                            </Badge>
                            View Thread
                          </Box>
                          <AccordionIcon />
                        </AccordionButton>
                        <AccordionPanel pb={4}>
                          {threadConversations[thread.thread_id] ? (
                            renderThreadConversations(threadConversations[thread.thread_id])
                          ) : (
                            <Text fontSize="sm" color="gray.500" textAlign="center">
                              Loading conversations...
                            </Text>
                          )}
                        </AccordionPanel>
                      </AccordionItem>
                    </Accordion>
                  )}
                </Box>
              </CardBody>
            </Card>
          ))
        )}
      </VStack>
    </Box>
  );
};

export default ConversationHistory; 