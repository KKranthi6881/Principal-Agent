import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Custom hook for monitoring lineage extraction tasks and managing the UI response
 * 
 * @param {Function} setSyncModalTab - Function to set the sync modal tab index
 * @returns {Object} Monitoring functions and state
 */
const useLineageMonitoring = (setSyncModalTab) => {
  const [lineageTasks, setLineageTasks] = useState([]);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [hasActiveTasks, setHasActiveTasks] = useState(false);
  // Use ref to track active state without causing re-renders
  const hasActiveTasksRef = useRef(false);

  // Function to fetch lineage tasks
  const fetchLineageTasks = useCallback(async () => {
    try {
      const response = await fetch('/api/lineage/tasks');
      if (!response.ok) {
        console.error('Failed to fetch lineage tasks:', response.status);
        return [];
      }
      
      const data = await response.json();
      const tasksArray = data.tasks || [];
      setLineageTasks(tasksArray);
      
      // Check if we have any running tasks
      const runningTasks = tasksArray.filter(task => task.status === 'running');
      setHasActiveTasks(runningTasks.length > 0);
      hasActiveTasksRef.current = runningTasks.length > 0;
      
      return tasksArray;
    } catch (error) {
      console.error('Error fetching lineage tasks:', error);
      return [];
    }
  }, []);

  // Function to start monitoring lineage tasks
  const startMonitoring = useCallback(() => {
    setIsMonitoring(true);
  }, []);

  // Function to notify user of new tasks and switch tab
  const notifyNewTask = useCallback(() => {
    // Switch to the lineage tab
    if (setSyncModalTab) {
      setSyncModalTab(1); // Index 1 is the lineage tab
    }
  }, [setSyncModalTab]);

  // Effect to monitor tasks
  useEffect(() => {
    if (!isMonitoring) return;

    let intervalId;
    let isUnmounting = false;
    
    const monitorTasks = async () => {
      if (isUnmounting) return;
      
      const tasks = await fetchLineageTasks();
      
      // If we found running tasks, check if we should switch tabs
      if (!isUnmounting && tasks.filter(task => task.status === 'running').length > 0) {
        notifyNewTask();
      }
      
      // If we have active tasks, poll more frequently (every 5 seconds)
      // Otherwise, poll less frequently (every 30 seconds)
      // Use the ref value instead of the state to avoid infinite re-renders
      const pollInterval = hasActiveTasksRef.current ? 5000 : 30000;
      
      // Clear any existing interval
      if (intervalId) {
        clearTimeout(intervalId);
      }
      
      // Set the next polling interval
      intervalId = setTimeout(monitorTasks, pollInterval);
    };
    
    // Start monitoring
    monitorTasks();
    
    return () => {
      isUnmounting = true;
      if (intervalId) {
        clearTimeout(intervalId);
      }
    };
  }, [isMonitoring, fetchLineageTasks, notifyNewTask]); // Remove hasActiveTasks from deps

  return {
    lineageTasks,
    isMonitoring,
    hasActiveTasks,
    startMonitoring,
    fetchLineageTasks,
    notifyNewTask
  };
};

export default useLineageMonitoring; 