import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Card,
  CardBody,
  Text,
  Progress,
  Grid,
  Button,
  Alert,
  AlertIcon,
  Tooltip,
  Flex,
  Spinner,
  useToast,
  Heading,
  Stack,
  Badge,
  Divider,
  HStack,
  VStack,
} from '@chakra-ui/react';
import { 
  IoRefresh, 
  IoCheckmarkCircle, 
  IoCloseCircle, 
  IoTimeOutline,
  IoInformationCircle,
  IoTrash,
  IoStop,
} from 'react-icons/io5';

const LineageTaskMonitor = () => {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const toast = useToast();
  const hasRunningTasksRef = useRef(false);
  const pollingIntervalRef = useRef(null);

  // Fetch tasks data from API
  const fetchData = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/lineage/tasks');
      if (!response.ok) {
        throw new Error(`Failed to fetch tasks: ${response.status} ${response.statusText}`);
      }
      const data = await response.json();
      setTasks(data.tasks || []);
      
      // Check if any tasks are running and update ref
      hasRunningTasksRef.current = (data.tasks || []).some(task => task.status === 'running');
      
      setError(null);
    } catch (err) {
      console.error('Error fetching lineage tasks:', err);
      setError(err.message);
      
      toast({
        title: "Error fetching tasks",
        description: err.message,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setLoading(false);
    }
  };

  // Setup polling with proper cleanup
  const setupPolling = () => {
    // Clear any existing interval
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }
    
    // Start a new polling interval
    fetchData(); // Initial fetch
    
    pollingIntervalRef.current = setInterval(() => {
      // Only continue polling if component is mounted and we have running tasks
      if (hasRunningTasksRef.current) {
        fetchData();
      }
    }, 5000);
  };

  // Initial fetch and setup refresh interval
  useEffect(() => {
    setupPolling();
    
    return () => {
      // Cleanup polling on unmount
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, []); // Empty dependency array

  // Handle manual refresh
  const handleRefresh = () => {
    setLoading(true);
    fetchData();
  };
  
  // Handle clearing history (completed and failed tasks)
  const handleClearHistory = async () => {
    try {
      const response = await fetch('/api/lineage/tasks/clear-history', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      if (response.ok) {
        toast({
          title: 'Task history cleared',
          description: 'Completed and failed tasks have been removed.',
          status: 'success',
          duration: 3000,
          isClosable: true,
        });
        fetchData();
      } else {
        throw new Error('Failed to clear task history');
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to clear task history',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  };
  
  // Handle stopping a running task
  const handleStopTask = async (taskId) => {
    try {
      const response = await fetch(`/api/lineage/tasks/${taskId}/stop`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      if (response.ok) {
        toast({
          title: 'Task stopped',
          description: 'The task has been stopped.',
          status: 'info',
          duration: 3000,
          isClosable: true,
        });
        fetchData();
      } else {
        throw new Error('Failed to stop task');
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to stop task',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  };

  // Get status icon based on task status
  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <IoCheckmarkCircle color="green" />;
      case 'failed':
        return <IoCloseCircle color="red" />;
      case 'running':
        return <Spinner size="sm" color="blue.500" speed="0.8s" />;
      default:
        return <IoTimeOutline color="gray" />;
    }
  };
  
  // Get step label based on current_step
  const getStepLabel = (step) => {
    if (!step) return 'Processing';
    
    // Convert snake_case to readable format
    return step
      .replace(/_/g, ' ')
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };
  
  // Get a human-readable operation description
  const getOperationDescription = (task) => {
    // First check if there's a current_operation in metadata
    if (task.metadata && task.metadata.current_operation) {
      return task.metadata.current_operation;
    }
    
    // Fallbacks based on step/status
    if (task.status === 'running') {
      return task.current_step 
        ? `${getStepLabel(task.current_step)}` 
        : 'Processing';
    } else if (task.status === 'completed') {
      return 'Processing completed successfully';
    } else if (task.status === 'failed') {
      return task.error || 'Processing failed';
    }
    
    return 'Unknown status';
  };

  // Format elapsed time
  const formatElapsedTime = (seconds) => {
    const date = new Date();
    date.setSeconds(date.getSeconds() - seconds);
    
    // Calculate time difference
    const now = new Date();
    const diff = Math.abs(Math.round((now - date) / 1000));
    
    if (diff < 60) {
      return `${diff} seconds ago`;
    } else if (diff < 3600) {
      return `${Math.floor(diff / 60)} minutes ago`;
    } else {
      return `${Math.floor(diff / 3600)} hours ago`;
    }
  };

  return (
    <Box mt={4} mb={8}>
      <Flex justifyContent="space-between" alignItems="center" mb={4}>
        <Heading size="md">Lineage Extraction Tasks</Heading>
        <HStack spacing={2}>
          {(tasks.filter(task => task.status === 'completed' || task.status === 'failed').length > 0) && (
            <Button 
              leftIcon={<IoTrash />} 
              onClick={handleClearHistory} 
              isDisabled={loading}
              size="sm"
              variant="outline"
              colorScheme="red"
            >
              Clear History
            </Button>
          )}
          <Button 
            leftIcon={<IoRefresh />} 
            onClick={handleRefresh} 
            isDisabled={loading}
            size="sm"
            variant="outline"
          >
            Refresh
          </Button>
        </HStack>
      </Flex>

      {loading && tasks.length === 0 && (
        <Progress isIndeterminate my={4} />
      )}

      {tasks.length === 0 && !loading ? (
        <Alert status="info" mt={4}>
          <AlertIcon />
          No lineage extraction tasks found.
        </Alert>
      ) : (
        <>
          {/* Group and display running tasks first */}
          {tasks.filter(task => task.status === 'running').length > 0 && (
            <Box mb={6}>
              <Heading size="sm" mb={3} color="blue.600">
                Currently Running
              </Heading>
              <Grid templateColumns="1fr" gap={4}>
                {tasks
                  .filter(task => task.status === 'running')
                  .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                  .map((task) => (
                    <Card key={task.task_id} variant="elevated" borderColor="blue.300" borderWidth="1px">
                      <CardBody>
                        <Flex justifyContent="space-between" alignItems="center">
                          <HStack spacing={2}>
                            {getStatusIcon(task.status)}
                            <Tooltip label={task.repo_url}>
                              <Text fontWeight="bold">
                                {task.metadata?.display_name || task.repo_url?.split('/').pop() || 'Unknown Repository'}
                              </Text>
                            </Tooltip>
                            <Badge colorScheme={
                              task.tech_stack === 'postgresql' ? 'blue' : 
                              task.tech_stack === 'mysql' ? 'orange' : 
                              task.tech_stack === 'snowflake' ? 'cyan' : 
                              task.tech_stack === 'tsql' ? 'purple' : 
                              task.tech_stack === 'dbt' ? 'green' : 'gray'
                            }>
                              {task.tech_stack}
                            </Badge>
                          </HStack>
                          <HStack>
                            <Button
                              size="xs"
                              leftIcon={<IoStop />}
                              colorScheme="red"
                              variant="outline"
                              onClick={() => handleStopTask(task.task_id)}
                            >
                              Stop
                            </Button>
                            <Text fontSize="sm" color="blue.500" fontWeight="medium">
                              Running • {formatElapsedTime(task.elapsed_seconds)}
                            </Text>
                          </HStack>
                        </Flex>
                        
                        <Box mt={3} mb={2}>
                          <Text fontSize="sm" color="gray.600" mb={1}>
                            {getOperationDescription(task)}
                          </Text>
                          <Progress 
                            value={task.progress || (task.total_items > 0 ? (task.processed_items / task.total_items) * 100 : 10)} 
                            colorScheme="blue"
                            size="sm"
                            borderRadius="full"
                            isAnimated={true}
                            hasStripe={true}
                          />
                        </Box>
                        
                        <Flex justifyContent="space-between" mt={3}>
                          <Text fontSize="sm">
                            {task.processed_files || task.processed_items || 0} / {task.total_files || task.total_items || '?'} items processed
                          </Text>
                          <Text fontSize="sm">
                            {task.successful_files || task.successful_items || 0} successful • {task.failed_files || task.failed_items || 0} failed
                          </Text>
                        </Flex>
                      </CardBody>
                    </Card>
                  ))
                }
              </Grid>
            </Box>
          )}
          
          {/* Group and display completed tasks */}
          {tasks.filter(task => task.status === 'completed').length > 0 && (
            <Box mb={6}>
              <Heading size="sm" mb={3} color="green.600">
                Completed
              </Heading>
              <Grid templateColumns="1fr" gap={3}>
                {tasks
                  .filter(task => task.status === 'completed')
                  .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                  .map((task) => (
                    <Card key={task.task_id} variant="outline" bg="gray.50">
                      <CardBody py={3}>
                        <Flex justifyContent="space-between" alignItems="center">
                          <HStack spacing={2}>
                            {getStatusIcon(task.status)}
                            <Text>
                              {task.metadata?.display_name || task.repo_url?.split('/').pop() || 'Unknown Repository'}
                            </Text>
                            <Badge size="sm" colorScheme="green">
                              {task.tech_stack}
                            </Badge>
                          </HStack>
                          <Text fontSize="sm" color="gray.500">
                            {formatElapsedTime(task.elapsed_seconds)}
                          </Text>
                        </Flex>
                        
                        <Flex justifyContent="space-between" fontSize="sm" color="gray.600" mt={2}>
                          <Text>
                            {task.total_items || 0} items processed • {task.successful_items || 0} successful
                          </Text>
                          {task.metadata?.completed_at && (
                            <Text>
                              {new Date(task.metadata.completed_at).toLocaleTimeString()}
                            </Text>
                          )}
                        </Flex>
                      </CardBody>
                    </Card>
                  ))
                }
              </Grid>
            </Box>
          )}
          
          {/* Group and display failed tasks */}
          {tasks.filter(task => task.status === 'failed').length > 0 && (
            <Box>
              <Heading size="sm" mb={3} color="red.600">
                Failed
              </Heading>
              <Grid templateColumns="1fr" gap={3}>
                {tasks
                  .filter(task => task.status === 'failed')
                  .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                  .map((task) => (
                    <Card key={task.task_id} variant="outline" borderColor="red.200">
                      <CardBody py={3}>
                        <Flex justifyContent="space-between" alignItems="center">
                          <HStack spacing={2}>
                            {getStatusIcon(task.status)}
                            <Text>
                              {task.metadata?.display_name || task.repo_url?.split('/').pop() || 'Unknown Repository'}
                            </Text>
                            <Badge size="sm" colorScheme="red">
                              {task.tech_stack}
                            </Badge>
                          </HStack>
                          <Text fontSize="sm" color="gray.500">
                            {formatElapsedTime(task.elapsed_seconds)}
                          </Text>
                        </Flex>
                        
                        <Box mt={2}>
                          <Text fontSize="sm" color="red.500">
                            {task.error || task.metadata?.error_details || 'Processing failed'}
                          </Text>
                        </Box>
                      </CardBody>
                    </Card>
                  ))
                }
              </Grid>
            </Box>
          )}
        </>
      )}
    </Box>
  );
};

export default LineageTaskMonitor; 