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
  Badge
} from '@chakra-ui/react';
import { 
  IoRefresh, 
  IoCheckmarkCircle, 
  IoCloseCircle, 
  IoTimeOutline 
} from 'react-icons/io5';

const LineageTaskMonitor = () => {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const toast = useToast();
  const hasRunningTasksRef = useRef(false);
  const pollingIntervalRef = useRef(null);

  // Fetch tasks data from API
  const fetchTasks = async () => {
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
    fetchTasks(); // Initial fetch
    
    pollingIntervalRef.current = setInterval(() => {
      // Only continue polling if component is mounted and we have running tasks
      if (hasRunningTasksRef.current) {
        fetchTasks();
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
    fetchTasks();
  };

  // Get status icon based on task status
  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <IoCheckmarkCircle color="green" />;
      case 'failed':
        return <IoCloseCircle color="red" />;
      case 'running':
        return <IoTimeOutline color="blue" />;
      default:
        return <IoTimeOutline color="gray" />;
    }
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
        <Button 
          leftIcon={<IoRefresh />} 
          onClick={handleRefresh} 
          isDisabled={loading}
          size="sm"
          variant="outline"
        >
          Refresh
        </Button>
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
        <Grid templateColumns="1fr" gap={4}>
          {tasks.map((task) => (
            <Card key={task.task_id} variant="outline">
              <CardBody>
                <Flex justifyContent="space-between" alignItems="center" mb={2}>
                  <Flex alignItems="center">
                    {getStatusIcon(task.status)}
                    <Text fontWeight="bold" ml={2}>
                      {task.repo_url ? task.repo_url.split('/').pop() : 'Unknown Repository'}
                    </Text>
                    <Badge ml={2} colorScheme={
                      task.tech_stack === 'postgresql' ? 'blue' : 
                      task.tech_stack === 'mysql' ? 'orange' : 
                      task.tech_stack === 'snowflake' ? 'cyan' : 
                      task.tech_stack === 'tsql' ? 'purple' : 'gray'
                    }>
                      {task.tech_stack}
                    </Badge>
                  </Flex>
                  <Tooltip label={task.status === 'running' ? 'Task is still running' : `Task ${task.status}`}>
                    <Text fontSize="sm" color="gray.500">
                      {formatElapsedTime(task.elapsed_seconds)}
                    </Text>
                  </Tooltip>
                </Flex>
                
                <Box my={3}>
                  <Progress 
                    value={task.total_files > 0 ? (task.processed_files / task.total_files) * 100 : 0} 
                    colorScheme={task.status === 'failed' ? 'red' : task.status === 'completed' ? 'green' : 'blue'}
                    size="sm"
                    borderRadius="full"
                  />
                </Box>
                
                <Flex justifyContent="space-between" mt={2}>
                  <Text fontSize="sm" color="gray.600">
                    {task.processed_files} / {task.total_files} files processed
                  </Text>
                  <Text fontSize="sm" color="gray.600">
                    {task.successful_files} successful • {task.failed_files} failed
                  </Text>
                </Flex>
                
                {task.error && (
                  <Alert status="error" mt={4} size="sm">
                    <AlertIcon />
                    {task.error}
                  </Alert>
                )}
              </CardBody>
            </Card>
          ))}
        </Grid>
      )}
    </Box>
  );
};

export default LineageTaskMonitor; 