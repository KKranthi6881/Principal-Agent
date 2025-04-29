import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Container,
  Heading,
  Text,
  Button,
  VStack,
  HStack,
  FormControl,
  FormLabel,
  Input,
  Select,
  Switch,
  FormErrorMessage,
  Divider,
  useToast,
  Card,
  CardHeader,
  CardBody,
  CardFooter,
  Flex,
  Tag,
  TagLabel,
  Badge,
  useDisclosure,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalFooter,
  ModalBody,
  ModalCloseButton,
  Textarea,
  IconButton,
  Popover,
  PopoverTrigger,
  PopoverContent,
  PopoverHeader,
  PopoverBody,
  PopoverFooter,
  PopoverArrow,
  PopoverCloseButton,
  Tooltip,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  Spinner,
  Accordion,
  AccordionItem,
  AccordionButton,
  AccordionPanel,
  AccordionIcon,
  List,
  ListItem,
  Link,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Grid,
  GridItem,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  SimpleGrid,
  Icon,
  Progress,
  Circle
} from '@chakra-ui/react';
import {
  IoCheckmarkCircle,
  IoCloseCircle,
  IoAddCircle,
  IoTrash,
  IoSettings,
  IoRefresh,
  IoInformationCircle,
  IoGitBranch,
  IoWarning,
  IoSearch,
  IoLink,
  IoUnlink,
  IoLockClosed,
  IoLogoGithub,
  IoServer,
  IoPerson,
  IoCode,
  IoCheckmark,
  IoClose
} from 'react-icons/io5';
import { FaDatabase } from 'react-icons/fa';
import LineageTaskMonitor from '../components/LineageTaskMonitor.jsx';
import useLineageMonitoring from '../hooks/useLineageMonitoring.jsx';

const GitHubConnectors = () => {
  const [connectors, setConnectors] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [testStatus, setTestStatus] = useState(null);
  const [selectedConnector, setSelectedConnector] = useState(null);
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const deleteConfirmRef = React.useRef();
  
  // Form state for creating/editing connectors
  const [form, setForm] = useState({
    name: '',
    description: '',
    github_type: 'public',
    api_url: '',
    token: '',
    owner: '',
    organization: '',
    repositories: '',
    default_branch: 'main',
    active: true,
    repo_url: '',
    tech_stack: 'postgresql'
  });
  
  // Form errors
  const [errors, setErrors] = useState({});
  
  // Vector sync modal state
  const [isVectorSyncModalOpen, setIsVectorSyncModalOpen] = useState(false);
  const [selectedVectorConnector, setSelectedVectorConnector] = useState(null);
  const [selectedEmbeddingProvider, setSelectedEmbeddingProvider] = useState('openai-small');
  const [embedddingProviders, setEmbeddingProviders] = useState([]);
  const [isLoadingProviders, setIsLoadingProviders] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [forceFullSync, setForceFullSync] = useState(false);
  const [syncModalTab, setSyncModalTab] = useState(0);
  
  // Sync status tracking
  const [syncStatuses, setSyncStatuses] = useState({});
  const [pollingActive, setPollingActive] = useState(false);
  const pollingRef = useRef(null);
  
  // Initialize lineage monitoring hook
  const lineageMonitoring = useLineageMonitoring(setSyncModalTab);
  
  // Fetch connectors on component mount
  useEffect(() => {
    fetchConnectors();
    fetchEmbeddingProviders();
    
    // Start polling for sync statuses
    setPollingActive(true);
    
    // Start monitoring lineage tasks
    lineageMonitoring.startMonitoring();
    
    return () => {
      // Clean up polling interval on component unmount
      setPollingActive(false);
      if (pollingRef.current) {
        clearTimeout(pollingRef.current);
      }
    };
  }, []);
  
  // Set up polling for sync statuses
  useEffect(() => {
    const pollSyncStatuses = async () => {
      if (!pollingActive) return;
      
      try {
        await fetchSyncStatuses();
        
        // Poll less frequently (10 seconds) to reduce load
        pollingRef.current = setTimeout(pollSyncStatuses, 50000);
      } catch (error) {
        console.error('Error in polling sync statuses:', error);
        // Wait for a little longer before trying again after an error
        pollingRef.current = setTimeout(pollSyncStatuses, 50000);
      }
    };
    
    pollSyncStatuses();
    
    return () => {
      if (pollingRef.current) {
        clearTimeout(pollingRef.current);
      }
    };
  }, [pollingActive]);
  
  // Fetch sync statuses for all connectors
  const fetchSyncStatuses = async () => {
    try {
      const response = await fetch('/api/github/syncs?limit=50');
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      const data = await response.json();
      
      // Group syncs by connector_id and repo_url
      const statusMap = {};
      
      if (data.syncs && data.syncs.length > 0) {
        data.syncs.forEach(sync => {
          const key = `${sync.connector_id}_${sync.repo_url}_${sync.embedding_provider}`;
          
          // Only keep the most recent sync for each connector+repo+provider combination
          if (!statusMap[key] || new Date(sync.sync_timestamp) > new Date(statusMap[key].sync_timestamp)) {
            statusMap[key] = sync;
          }
        });
      }
      
      setSyncStatuses(statusMap);
    } catch (error) {
      console.error('Error fetching sync statuses:', error);
    }
  };
  
  // Get sync status for a specific connector and provider
  const getSyncStatus = (connector) => {
    // Create a repo URL if it's not directly available
    let repoUrl = connector.repo_url || '';
    
    if (!repoUrl && connector.github_type === 'public') {
      if (connector.repositories && connector.repositories.length > 0) {
        const firstRepo = connector.repositories[0];
        if (firstRepo.includes('/')) {
          repoUrl = `https://github.com/${firstRepo}`;
        } else if (connector.owner) {
          repoUrl = `https://github.com/${connector.owner}/${firstRepo}`;
        }
      } else if (connector.owner) {
        repoUrl = `https://github.com/${connector.owner}/${connector.name.replace(/\s+/g, '-').toLowerCase()}`;
      }
    }
    
    if (!repoUrl) return null;
    
    const key = `${connector.id}_${repoUrl}_${selectedEmbeddingProvider}`;
    return syncStatuses[key];
  };
  
  // Check if a sync is active for a connector
  const isConnectorSyncing = (connector) => {
    const providers = ["openai-small", "openai-large", "ollama"];
    
    return providers.some(provider => {
      const status = getSyncStatus(connector);
      return status && status.status === 'in_progress';
    });
  };
  
  // Get the most recent sync for a connector across all providers
  const getMostRecentSync = (connector) => {
    const providers = ["openai-small", "openai-large", "ollama"];
    let mostRecent = null;
    
    providers.forEach(provider => {
      const status = getSyncStatus(connector);
      if (status && (!mostRecent || new Date(status.sync_timestamp) > new Date(mostRecent.sync_timestamp))) {
        mostRecent = status;
      }
    });
    
    return mostRecent;
  };
  
  // Fetch all GitHub connectors
  const fetchConnectors = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('/api/settings/github_connectors');
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      const data = await response.json();
      setConnectors(data.connectors || []);
      
      // After fetching connectors, fetch sync statuses
      fetchSyncStatuses();
    } catch (error) {
      console.error('Error fetching GitHub connectors:', error);
      toast({
        title: 'Error fetching connectors',
        description: error.message,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsLoading(false);
    }
  };
  
  // Fetch embedding providers
  const fetchEmbeddingProviders = async () => {
    setIsLoadingProviders(true);
    try {
      const response = await fetch('/api/github/providers');
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      const data = await response.json();
      setEmbeddingProviders(data.providers || []);
    } catch (error) {
      console.error('Error fetching embedding providers:', error);
      toast({
        title: 'Error fetching embedding providers',
        description: error.message,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsLoadingProviders(false);
    }
  };
  
  // Handle form input change
  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    const val = type === 'checkbox' ? checked : value;
    
    setForm({
      ...form,
      [name]: val
    });
    
    // Clear error for this field
    if (errors[name]) {
      setErrors({
        ...errors,
        [name]: null
      });
    }
  };
  
  // Validate form
  const validateForm = () => {
    const newErrors = {};
    
    if (!form.name.trim()) {
      newErrors.name = 'Name is required';
    }
    
    if (!form.token.trim()) {
      newErrors.token = 'Token is required';
    }
    
    if (form.github_type === 'public' && !form.repo_url.trim()) {
      newErrors.repo_url = 'Repository URL is required for public GitHub';
    }
    
    if (form.github_type === 'enterprise' && !form.api_url.trim()) {
      newErrors.api_url = 'API URL is required for enterprise GitHub';
    }
    
    // Validate API URL format if provided
    if (form.api_url.trim() && !form.api_url.trim().startsWith('http')) {
      newErrors.api_url = 'API URL must start with http:// or https://';
    }
    
    // Validate Repository URL format if provided
    if (form.repo_url.trim() && !form.repo_url.trim().startsWith('http')) {
      newErrors.repo_url = 'Repository URL must start with http:// or https://';
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };
  
  // Test GitHub connection
  const testConnection = async () => {
    if (!validateForm()) {
      return;
    }
    
    setIsTestingConnection(true);
    setTestStatus(null);
    
    try {
      // Prepare request body
      const requestBody = {
        ...form,
        repositories: form.repositories ? form.repositories.split(',').map(repo => repo.trim()) : null
      };
      
      // Log the request body (but hide the token for security)
      const sanitizedRequestBody = { ...requestBody };
      sanitizedRequestBody.token = sanitizedRequestBody.token ? '***REDACTED***' : null;
      console.log('Testing GitHub connection with:', sanitizedRequestBody);
      
      const response = await fetch('/api/settings/github_connectors/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      });
      
      console.log('GitHub test response status:', response.status);
      
      const data = await response.json();
      console.log('GitHub test response data:', data);
      
      if (response.ok && data.success) {
        setTestStatus({
          success: true,
          message: data.message,
          details: data.details
        });
        
        toast({
          title: 'Connection Successful',
          description: 'Successfully connected to GitHub',
          status: 'success',
          duration: 3000,
          isClosable: true,
        });
        
        // Auto-fill owner/organization if not already provided
        if (data.details && data.details.user) {
          if (!form.owner && !form.organization) {
            setForm({
              ...form,
              owner: data.details.user.login
            });
          }
        }
      } else {
        setTestStatus({
          success: false,
          message: data.message || 'Connection failed',
          details: data.details
        });
        
        toast({
          title: 'Connection Failed',
          description: data.message || 'Failed to connect to GitHub',
          status: 'error',
          duration: 5000,
          isClosable: true,
        });
      }
    } catch (error) {
      console.error('Error testing GitHub connection:', error);
      
      setTestStatus({
        success: false,
        message: error.message,
        details: null
      });
      
      toast({
        title: 'Error Testing Connection',
        description: error.message,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsTestingConnection(false);
    }
  };
  
  // Submit form to create/update connector
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!validateForm()) {
      return;
    }
    
    // Require connection test before saving
    if (!testStatus || !testStatus.success) {
      toast({
        title: 'Test Connection Required',
        description: 'Please test the connection before saving',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    
    setIsSubmitting(true);
    
    try {
      // Prepare request body
      const requestBody = {
        ...form,
        repositories: form.repositories ? form.repositories.split(',').map(repo => repo.trim()) : null
      };
      
      let response;
      
      if (selectedConnector) {
        // Update existing connector
        response = await fetch(`/api/settings/github_connectors/${selectedConnector.id}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(requestBody)
        });
      } else {
        // Create new connector
        response = await fetch('/api/settings/github_connectors', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(requestBody)
        });
      }
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }
      
      const data = await response.json();
      
      toast({
        title: selectedConnector ? 'Connector Updated' : 'Connector Created',
        description: `Successfully ${selectedConnector ? 'updated' : 'created'} GitHub connector "${data.name}"`,
        status: 'success',
        duration: 3000,
        isClosable: true,
      });
      
      // Reset form and refresh connectors
      resetForm();
      fetchConnectors();
      
    } catch (error) {
      console.error('Error saving GitHub connector:', error);
      
      toast({
        title: 'Error Saving Connector',
        description: error.message,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsSubmitting(false);
    }
  };
  
  // Reset form to initial state
  const resetForm = () => {
    setForm({
      name: '',
      description: '',
      github_type: 'public',
      api_url: '',
      token: '',
      owner: '',
      organization: '',
      repositories: '',
      default_branch: 'main',
      active: true,
      repo_url: '',
      tech_stack: 'postgresql'
    });
    setErrors({});
    setTestStatus(null);
    setSelectedConnector(null);
  };
  
  // Edit connector
  const handleEdit = (connector) => {
    // Convert array of repositories back to comma-separated string
    const repoString = connector.repositories ? connector.repositories.join(', ') : '';
    
    setForm({
      name: connector.name,
      description: connector.description || '',
      github_type: connector.github_type,
      api_url: connector.api_url || '',
      token: '', // Don't populate the token - require the user to enter it again
      owner: connector.owner || '',
      organization: connector.organization || '',
      repositories: repoString,
      default_branch: connector.default_branch || 'main',
      active: connector.active,
      repo_url: connector.repo_url || '',
      tech_stack: connector.tech_stack || 'postgresql'
    });
    
    setSelectedConnector(connector);
    setTestStatus(null); // Reset test status for the new form
  };
  
  // Open delete confirmation
  const confirmDelete = (connector) => {
    setSelectedConnector(connector);
    onOpen();
  };
  
  // Delete connector
  const handleDelete = async () => {
    if (!selectedConnector) return;
    
    try {
      const response = await fetch(`/api/settings/github_connectors/${selectedConnector.id}`, {
        method: 'DELETE'
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }
      
      toast({
        title: 'Connector Deleted',
        description: `Successfully deleted GitHub connector "${selectedConnector.name}"`,
        status: 'success',
        duration: 3000,
        isClosable: true,
      });
      
      // Reset state and refresh connectors
      setSelectedConnector(null);
      onClose();
      fetchConnectors();
      
    } catch (error) {
      console.error('Error deleting GitHub connector:', error);
      
      toast({
        title: 'Error Deleting Connector',
        description: error.message,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  };
  
  // Handle vector sync button click
  const handleVectorSync = (connector) => {
    setSelectedVectorConnector(connector);
    setIsVectorSyncModalOpen(true);
    // Start with vector sync tab (index 0)
    setSyncModalTab(0);
    // Fetch the latest lineage tasks
    lineageMonitoring.fetchLineageTasks();
  };
  
  // Start vector sync
  const startVectorSync = async () => {
    if (!selectedVectorConnector) return;
    
    setIsSyncing(true);
    setSyncResult(null);
    
    try {
      // Build the request
      const request = {
        connector_id: selectedVectorConnector.id,
        repo_url: selectedVectorConnector.repo_url || '', // Use repo_url if available
        embedding_provider: selectedEmbeddingProvider,
        force_full_sync: forceFullSync,
        branch: selectedVectorConnector.default_branch || 'main'
      };
      
      // If repo_url is not available, construct it from other fields
      if (!request.repo_url && selectedVectorConnector.github_type === 'public') {
        // Handle different repository formats
        if (selectedVectorConnector.repositories && selectedVectorConnector.repositories.length > 0) {
          const firstRepo = selectedVectorConnector.repositories[0];
          if (firstRepo.includes('/')) {
            // It's already in owner/repo format
            request.repo_url = `https://github.com/${firstRepo}`;
          } else if (selectedVectorConnector.owner) {
            // We have owner and repo separately
            request.repo_url = `https://github.com/${selectedVectorConnector.owner}/${firstRepo}`;
          }
        } else if (selectedVectorConnector.owner) {
          // For older connectors that might not have repositories defined
          request.repo_url = `https://github.com/${selectedVectorConnector.owner}/${selectedVectorConnector.name.replace(/\s+/g, '-').toLowerCase()}`;
        }
      }
      
      // Make sure we have a repo URL
      if (!request.repo_url) {
        throw new Error("No repository URL available for sync");
      }
      
      // Call the API
      const response = await fetch('/api/github/sync', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(request)
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        // Handle specific error cases
        if (data.detail && data.detail.includes("OpenAI API key is required")) {
          throw new Error("OpenAI API key is missing. Please add an OpenAI provider in Settings > LLM Providers.");
        } else if (data.detail && data.detail.includes("Ollama")) {
          throw new Error("Ollama connection error. Make sure Ollama is running on your machine.");
        } else {
          throw new Error(data.detail || `API error: ${response.status}`);
        }
      }
      
      // Set sync result
      setSyncResult({
        success: true,
        syncId: data.sync_id,
        message: `Sync started with ID ${data.sync_id}. Check status in background tasks.`,
        status: data.status,
        files_indexed: data.files_indexed || 0
      });
      
      toast({
        title: 'Vector Sync Started',
        description: `Sync process started for repository. This may take some time to complete.`,
        status: 'info',
        duration: 5000,
        isClosable: true,
      });
      
      // Immediately fetch sync statuses to update UI
      fetchSyncStatuses();
      
      // After successful vector sync, check for lineage tasks
      const tasks = await lineageMonitoring.fetchLineageTasks();
      
      // If we have active tasks, switch to lineage tab
      if (lineageMonitoring.hasActiveTasks) {
        // Wait a moment to allow UI to update first
        setTimeout(() => {
          setSyncModalTab(1);
          toast({
            title: "Lineage extraction in progress",
            description: "Switch to the Lineage Progress tab to monitor progress",
            status: "info",
            duration: 5000,
            isClosable: true,
          });
        }, 2000);
      }
      
    } catch (error) {
      console.error('Error starting vector sync:', error);
      
      // Create a more user-friendly error message with instructions
      let errorMessage = error.message;
      let detailedInstructions = "";
      
      if (error.message.includes("OpenAI API key")) {
        errorMessage = "OpenAI API key is required for OpenAI embeddings";
        detailedInstructions = `
          To configure an OpenAI provider:
          1. Go to Settings > LLM Providers
          2. Click "Add Provider"
          3. Select "OpenAI" as the provider
          4. Enter your API key from openai.com
          5. Click Save
        `;
      } else if (error.message.includes("Ollama")) {
        errorMessage = "Error connecting to Ollama. Please make sure Ollama is running on your machine.";
        detailedInstructions = `
          To use Ollama:
          1. Ensure Ollama is installed and running on your machine
          2. Verify Ollama is accessible at http://localhost:11434
        `;
      }
      
      setSyncResult({
        success: false,
        message: errorMessage,
        detailedInstructions: detailedInstructions,
        status: 'failed'
      });
      
      toast({
        title: 'Error Starting Vector Sync',
        description: errorMessage,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsSyncing(false);
    }
  };
  
  // Delete vectors
  const deleteVectors = async () => {
    if (!selectedVectorConnector) return;
    
    setIsSyncing(true);
    setSyncResult(null);
    
    try {
      // Build the request
      const request = {
        connector_id: selectedVectorConnector.id,
        repo_url: selectedVectorConnector.repo_url || '',
        embedding_provider: selectedEmbeddingProvider
      };
      
      // If repo_url is not available, construct it from other fields (same as in startVectorSync)
      if (!request.repo_url && selectedVectorConnector.github_type === 'public') {
        if (selectedVectorConnector.repositories && selectedVectorConnector.repositories.length > 0) {
          const firstRepo = selectedVectorConnector.repositories[0];
          if (firstRepo.includes('/')) {
            request.repo_url = `https://github.com/${firstRepo}`;
          } else if (selectedVectorConnector.owner) {
            request.repo_url = `https://github.com/${selectedVectorConnector.owner}/${firstRepo}`;
          }
        } else if (selectedVectorConnector.owner) {
          request.repo_url = `https://github.com/${selectedVectorConnector.owner}/${selectedVectorConnector.name.replace(/\s+/g, '-').toLowerCase()}`;
        }
      }
      
      // Make sure we have a repo URL
      if (!request.repo_url) {
        throw new Error("No repository URL available to delete");
      }
      
      // Call the API
      const response = await fetch('/api/github/delete', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(request)
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        // Handle specific error cases
        if (data.detail && data.detail.includes("OpenAI API key is required")) {
          throw new Error("OpenAI API key is missing. Please add an OpenAI provider in Settings > LLM Providers with a valid API key.");
        } else if (data.detail && data.detail.includes("Ollama")) {
          throw new Error("Ollama connection error. Make sure Ollama is running on your machine.");
        } else {
          throw new Error(data.detail || `API error: ${response.status}`);
        }
      }
      
      setSyncResult({
        success: data.success,
        message: data.message,
        status: data.success ? 'completed' : 'failed'
      });
      
      toast({
        title: data.success ? 'Vectors Deleted' : 'Error Deleting Vectors',
        description: data.message,
        status: data.success ? 'success' : 'error',
        duration: 5000,
        isClosable: true,
      });
      
    } catch (error) {
      console.error('Error deleting vectors:', error);
      
      // Create a more user-friendly error message
      let errorMessage = error.message;
      if (error.message.includes("OpenAI API key")) {
        errorMessage = "OpenAI API key is required. Please configure an OpenAI provider in Settings > LLM Providers.";
      } else if (error.message.includes("Ollama")) {
        errorMessage = "Error connecting to Ollama. Please make sure Ollama is running on your machine.";
      }
      
      setSyncResult({
        success: false,
        message: errorMessage,
        status: 'failed'
      });
      
      toast({
        title: 'Error Deleting Vectors',
        description: errorMessage,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsSyncing(false);
    }
  };
  
  // Close vector sync modal
  const closeVectorSyncModal = () => {
    setIsVectorSyncModalOpen(false);
    setSelectedVectorConnector(null);
    setSelectedEmbeddingProvider('openai-small');
    setSyncResult(null);
    setForceFullSync(false);
    setSyncModalTab(0); // Reset tab index when closing
  };
  
  // Vector Sync Modal Component
  const VectorSyncModal = () => (
    <Modal isOpen={isVectorSyncModalOpen} onClose={closeVectorSyncModal} size="xl">
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>
          Sync Repository with Vector Store
          {selectedVectorConnector && (
            <Text fontSize="sm" fontWeight="normal" mt={1}>
              {selectedVectorConnector.name}
            </Text>
          )}
        </ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <Tabs index={syncModalTab} onChange={(index) => setSyncModalTab(index)} variant="enclosed">
            <TabList>
              <Tab>Vector Sync</Tab>
              <Tab>Lineage Progress</Tab>
            </TabList>
            <TabPanels>
              <TabPanel>
                {/* Existing vector sync content */}
                {!syncResult ? (
                  <VStack spacing={4} align="stretch">
                    <FormControl>
                      <FormLabel>Embedding Provider</FormLabel>
                      <Select
                        value={selectedEmbeddingProvider}
                        onChange={(e) => setSelectedEmbeddingProvider(e.target.value)}
                        isDisabled={isSyncing || isLoadingProviders}
                      >
                        {embedddingProviders.map((provider) => (
                          <option key={provider.id} value={provider.id}>
                            {provider.name}
                          </option>
                        ))}
                      </Select>
                    </FormControl>
                    
                    <FormControl>
                      <FormLabel>Sync Options</FormLabel>
                      <Flex alignItems="center">
                        <Switch
                          id="force-full-sync"
                          isChecked={forceFullSync}
                          onChange={(e) => setForceFullSync(e.target.checked)}
                          isDisabled={isSyncing}
                          mr={2}
                        />
                        <FormLabel htmlFor="force-full-sync" mb={0}>
                          Force Full Sync (re-index all files)
                        </FormLabel>
                      </Flex>
                    </FormControl>
                    
                    <Divider />
                    
                    <Text fontSize="sm" color="gray.600">
                      This will scan the repository and index all code files in the vector store for
                      semantic search and AI analysis. This process may take several minutes depending
                      on the repository size.
                    </Text>
                    
                    {selectedVectorConnector && getMostRecentSync(selectedVectorConnector) && (
                      <Alert status="info" size="sm">
                        <AlertIcon />
                        <VStack align="start" spacing={0}>
                          <Text fontSize="sm">
                            Last synced: {new Date(getMostRecentSync(selectedVectorConnector).created_at).toLocaleString()}
                          </Text>
                          <Text fontSize="sm">
                            Files indexed: {getMostRecentSync(selectedVectorConnector).files_indexed || 0}
                          </Text>
                        </VStack>
                      </Alert>
                    )}
                  </VStack>
                ) : (
                  <VStack spacing={4} align="stretch">
                    <Alert
                      status={syncResult.success ? "success" : "error"}
                      variant="subtle"
                      flexDirection="column"
                      alignItems="center"
                      justifyContent="center"
                      textAlign="center"
                      height="200px"
                    >
                      <AlertIcon boxSize="40px" mr={0} />
                      <AlertTitle mt={4} mb={1} fontSize="lg">
                        {syncResult.success ? "Sync Successful!" : "Sync Failed"}
                      </AlertTitle>
                      <AlertDescription maxWidth="sm">
                        {syncResult.message}
                        {syncResult.files_indexed > 0 && (
                          <Text mt={2}>
                            {syncResult.files_indexed} files indexed
                          </Text>
                        )}
                      </AlertDescription>
                    </Alert>
                  </VStack>
                )}
              </TabPanel>
              <TabPanel>
                {/* Lineage extraction progress content */}
                <Box pt={2}>
                  <LineageTaskMonitor />
                </Box>
              </TabPanel>
            </TabPanels>
          </Tabs>
        </ModalBody>
        <ModalFooter>
          {!syncResult ? (
            <>
              <Button
                colorScheme="red"
                mr={3}
                leftIcon={<IoTrash />}
                onClick={deleteVectors}
                isDisabled={isSyncing}
                size="sm"
              >
                Delete Vectors
              </Button>
              <Button
                colorScheme="blue"
                leftIcon={<IoRefresh />}
                onClick={startVectorSync}
                isLoading={isSyncing}
                loadingText="Syncing..."
                size="sm"
              >
                Start Sync
              </Button>
            </>
          ) : (
            <Button colorScheme="blue" onClick={closeVectorSyncModal} size="sm">
              Close
            </Button>
          )}
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
  
  // Add this new function after the handleVectorSync function
  const startLineageExtraction = async (connector) => {
    try {
      // Show loading toast
      toast({
        title: "Starting lineage extraction",
        description: "Please wait while we analyze the repository structure...",
        status: "info",
        duration: 3000,
        isClosable: true,
      });
      
      // Make API call to start lineage extraction
      const response = await fetch(`/api/lineage/github-connector/${connector.id}/extract-lineage`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
      });
      
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || `Error ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      
      // Show success toast
      toast({
        title: "Lineage extraction started",
        description: "Processing SQL files in the background. See progress in the Lineage tab.",
        status: "success",
        duration: 5000,
        isClosable: true,
      });
      
      // Fetch the latest tasks
      setTimeout(() => {
        lineageMonitoring.fetchLineageTasks();
      }, 1000);
      
    } catch (error) {
      console.error("Error starting lineage extraction:", error);
      toast({
        title: "Error starting lineage extraction",
        description: error.message,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };
  
  // Render list of existing connectors
  const renderConnectorsList = () => {
    if (isLoading) {
      return (
        <Box p={5} textAlign="center">
          <Spinner size="xl" color="blue.500" />
          <Text mt={4}>Loading connectors...</Text>
        </Box>
      );
    }

    if (connectors.length === 0) {
      return (
        <Alert status="info" borderRadius="md" my={4}>
          <AlertIcon />
          <Box flex="1">
            <AlertTitle>No Connectors Found</AlertTitle>
            <AlertDescription>
              Add a GitHub connector to get started.
            </AlertDescription>
          </Box>
        </Alert>
      );
    }

    return (
      <Grid templateColumns={{base: "1fr", md: "repeat(2, 1fr)", lg: "repeat(3, 1fr)"}} gap={6}>
        {connectors.map((connector) => (
          <Card key={connector.id} boxShadow="md" borderRadius="lg" overflow="hidden">
            <CardHeader bg={connector.active ? "blue.50" : "gray.50"} p={4}>
              <Flex justifyContent="space-between" alignItems="center">
                <Heading size="md" color={connector.active ? "blue.700" : "gray.500"}>
                  {connector.name}
                </Heading>
                <Badge 
                  colorScheme={
                    connector.tech_stack === 'postgresql' ? 'blue' : 
                    connector.tech_stack === 'mysql' ? 'orange' : 
                    connector.tech_stack === 'snowflake' ? 'cyan' : 
                    connector.tech_stack === 'tsql' ? 'purple' :
                    connector.tech_stack === 'dbt' ? 'green' : 'gray'
                  }
                >
                  {connector.tech_stack}
                </Badge>
              </Flex>
            </CardHeader>
            
            <CardBody p={4}>
              <VStack align="start" spacing={3}>
                {connector.description && (
                  <Text fontSize="sm" color="gray.600">
                    {connector.description}
                  </Text>
                )}
                
                <Flex wrap="wrap" gap={2}>
                  <Tag size="sm" colorScheme={connector.github_type === 'public' ? 'green' : 'purple'}>
                    <TagLabel>{connector.github_type}</TagLabel>
                  </Tag>
                  
                  {connector.has_token && (
                    <Tag size="sm" colorScheme="blue">
                      <Icon as={IoLockClosed} mr={1} />
                      <TagLabel>Authenticated</TagLabel>
                    </Tag>
                  )}
                  
                  {connector.active ? (
                    <Tag size="sm" colorScheme="green">
                      <Icon as={IoCheckmarkCircle} mr={1} />
                      <TagLabel>Active</TagLabel>
                    </Tag>
                  ) : (
                    <Tag size="sm" colorScheme="red">
                      <Icon as={IoCloseCircle} mr={1} />
                      <TagLabel>Inactive</TagLabel>
                    </Tag>
                  )}
                </Flex>
                
                <Divider />
                
                <Box width="100%">
                  <Text fontWeight="bold" fontSize="sm" mb={2}>Repository</Text>
                  {connector.repo_url ? (
                    <Link href={connector.repo_url} isExternal color="blue.500" fontSize="sm">
                      <Flex alignItems="center">
                        <Icon as={IoLogoGithub} mr={1} />
                        {connector.repo_url.replace('https://github.com/', '').replace('.git', '')}
                      </Flex>
                    </Link>
                  ) : connector.owner && connector.repositories && connector.repositories.length > 0 ? (
                    <Link href={`https://github.com/${connector.owner}/${connector.repositories[0]}`} isExternal color="blue.500" fontSize="sm">
                      <Flex alignItems="center">
                        <Icon as={IoLogoGithub} mr={1} />
                        {connector.owner}/{connector.repositories[0]}
                      </Flex>
                    </Link>
                  ) : (
                    <Text fontSize="sm" color="gray.500">No repository URL specified</Text>
                  )}
                </Box>
                
                {/* Show sync status if available */}
                {getSyncStatus(connector) && (
                  <Box width="100%" mt={2}>
                    <Flex justifyContent="space-between" alignItems="center" mb={1}>
                      <Text fontSize="sm" fontWeight="bold">Vector Sync Status</Text>
                      <Badge 
                        colorScheme={
                          getSyncStatus(connector).state === 'completed' ? 'green' : 
                          getSyncStatus(connector).state === 'failed' ? 'red' : 'blue'
                        }
                        fontSize="xs"
                      >
                        {getSyncStatus(connector).state}
                      </Badge>
                    </Flex>
                    <Progress 
                      value={100} 
                      size="sm" 
                      colorScheme={
                        getSyncStatus(connector).state === 'completed' ? 'green' : 
                        getSyncStatus(connector).state === 'failed' ? 'red' : 'blue'
                      }
                      borderRadius="full"
                    />
                    <Flex justifyContent="space-between" mt={1}>
                      <Text fontSize="xs" color="gray.500">
                        {new Date(getSyncStatus(connector).created_at).toLocaleString()}
                      </Text>
                      <Text fontSize="xs" color="gray.500">
                        {getSyncStatus(connector).files_indexed || 0} files
                      </Text>
                    </Flex>
                  </Box>
                )}
              </VStack>
            </CardBody>
            
            <CardFooter bg="gray.50" p={4}>
              <Flex width="100%" justifyContent="space-between">
                <HStack>
                  <IconButton
                    icon={<IoSettings />}
                    aria-label="Edit connector"
                    size="sm"
                    colorScheme="blue"
                    variant="outline"
                    onClick={() => handleEdit(connector)}
                  />
                  <IconButton
                    icon={<IoTrash />}
                    aria-label="Delete connector"
                    size="sm"
                    colorScheme="red"
                    variant="outline"
                    onClick={() => confirmDelete(connector)}
                  />
                </HStack>
                
                <HStack>
                  {connector.active && (
                    <>
                      <Tooltip label="Extract Lineage">
                        <IconButton
                          icon={<IoGitBranch />}
                          aria-label="Extract Lineage"
                          size="sm"
                          colorScheme="green"
                          onClick={() => {
                            setSelectedVectorConnector(connector);
                            setIsVectorSyncModalOpen(true);
                            setSyncModalTab(1); // Switch to Lineage tab
                            // Start lineage extraction immediately
                            startLineageExtraction(connector);
                            // Then fetch tasks to show progress
                            lineageMonitoring.fetchLineageTasks();
                          }}
                        />
                      </Tooltip>
                      <Tooltip label="Sync with Vector Store">
                        <IconButton
                          icon={<IoRefresh />}
                          aria-label="Sync with Vector Store"
                          size="sm"
                          colorScheme="blue"
                          isLoading={isConnectorSyncing(connector)}
                          onClick={() => handleVectorSync(connector)}
                        />
                      </Tooltip>
                    </>
                  )}
                </HStack>
              </Flex>
            </CardFooter>
          </Card>
        ))}
      </Grid>
    );
  };
  
  // Render test connection results
  const renderTestResults = () => {
    if (!testStatus) return null;
    
    return (
      <Alert
        status={testStatus.success ? 'success' : 'error'}
        variant="subtle"
        flexDirection="column"
        alignItems="flex-start"
        mt={4}
        mb={6}
        borderRadius="md"
      >
        <HStack mb={2}>
          <AlertIcon />
          <AlertTitle>{testStatus.success ? 'Connection Successful' : 'Connection Failed'}</AlertTitle>
        </HStack>
        <AlertDescription>
          <Text mb={2}>{testStatus.message}</Text>
          
          {testStatus.success && testStatus.details && (
            <Box mt={2}>
              <Accordion allowToggle>
                <AccordionItem>
                  <AccordionButton>
                    <Box flex="1" textAlign="left" fontWeight="bold">
                      Connection Details
                    </Box>
                    <AccordionIcon />
                  </AccordionButton>
                  <AccordionPanel>
                    <VStack align="start" spacing={2}>
                      <HStack>
                        <Text fontWeight="bold">Authenticated User:</Text>
                        <Text>{testStatus.details.user?.login}</Text>
                        {testStatus.details.user?.name && (
                          <Text>({testStatus.details.user.name})</Text>
                        )}
                      </HStack>
                      
                      {testStatus.details.user?.email && (
                        <HStack>
                          <Text fontWeight="bold">Email:</Text>
                          <Text>{testStatus.details.user.email}</Text>
                        </HStack>
                      )}
                      
                      {testStatus.details.repositories && (
                        <Box width="100%">
                          <Text fontWeight="bold" mb={1}>
                            {testStatus.details.repositories.type === 'organization' ? 'Organization' : 
                             testStatus.details.repositories.type === 'user' ? 'User' : 
                             'Available'} Repositories:
                          </Text>
                          
                          {testStatus.details.repositories.name && (
                            <Text mb={2}>
                              {testStatus.details.repositories.type === 'organization' ? 'Org: ' : 'User: '}
                              <Badge colorScheme="purple">{testStatus.details.repositories.name}</Badge>
                            </Text>
                          )}
                          
                          <Box maxH="200px" overflowY="auto" borderWidth="1px" borderRadius="md" p={2}>
                            {testStatus.details.repositories.repositories.length > 0 ? (
                              <List spacing={1}>
                                {testStatus.details.repositories.repositories.map((repo, idx) => (
                                  <ListItem key={idx}>
                                    <HStack>
                                      <Icon as={IoCode} color="gray.500" />
                                      <Text>{repo}</Text>
                                    </HStack>
                                  </ListItem>
                                ))}
                              </List>
                            ) : (
                              <Text color="gray.500">No repositories found</Text>
                            )}
                          </Box>
                        </Box>
                      )}
                    </VStack>
                  </AccordionPanel>
                </AccordionItem>
              </Accordion>
            </Box>
          )}
        </AlertDescription>
      </Alert>
    );
  };
  
  return (
    <Container maxW="container.xl" py={8}>
      <Heading mb={8}>GitHub Connectors</Heading>
      
      <Tabs variant="enclosed">
        <TabList>
          <Tab>Connectors</Tab>
          <Tab>{selectedConnector ? 'Edit Connector' : 'Add Connector'}</Tab>
        </TabList>
        
        <TabPanels>
          <TabPanel>
            <Box mb={6}>
              <HStack justify="space-between" mb={4}>
                <Heading size="md">GitHub Connector List</Heading>
                <Button 
                  leftIcon={<IoAddCircle />} 
                  colorScheme="purple" 
                  onClick={resetForm}
                >
                  Add New Connector
                </Button>
              </HStack>
              {renderConnectorsList()}
            </Box>
          </TabPanel>
          
          <TabPanel>
            <Box mb={6}>
              <Heading size="md" mb={4}>
                {selectedConnector ? 'Edit GitHub Connector' : 'Add GitHub Connector'}
              </Heading>
              
              <Card variant="outline">
                <CardBody>
                  <form onSubmit={handleSubmit}>
                    <VStack spacing={4} align="stretch">
                      <FormControl isRequired isInvalid={!!errors.name}>
                        <FormLabel>Connector Name</FormLabel>
                        <Input 
                          name="name" 
                          placeholder="E.g., My GitHub Connection"
                          value={form.name}
                          onChange={handleChange}
                        />
                        <FormErrorMessage>{errors.name}</FormErrorMessage>
                      </FormControl>
                      
                      <FormControl>
                        <FormLabel>Description</FormLabel>
                        <Textarea 
                          name="description" 
                          placeholder="Optional description for this connector"
                          value={form.description}
                          onChange={handleChange}
                          resize="vertical"
                          rows={2}
                        />
                      </FormControl>
                      
                      <FormControl isRequired>
                        <FormLabel>GitHub Type</FormLabel>
                        <Select 
                          name="github_type" 
                          value={form.github_type}
                          onChange={handleChange}
                        >
                          <option value="public">Public GitHub (github.com)</option>
                          <option value="enterprise">Enterprise GitHub (custom domain)</option>
                        </Select>
                      </FormControl>
                      
                      <Box 
                        p={4} 
                        bg={form.github_type === 'public' ? 'blue.50' : 'orange.50'} 
                        borderRadius="md" 
                        mt={3}
                      >
                        <HStack mb={3}>
                          <Icon 
                            as={form.github_type === 'public' ? IoLogoGithub : IoServer} 
                            color={form.github_type === 'public' ? 'blue.500' : 'orange.500'}
                            boxSize={5}
                          />
                          <Text fontWeight="bold">
                            {form.github_type === 'public' 
                              ? 'Public GitHub Connection' 
                              : 'Enterprise GitHub Connection'}
                          </Text>
                        </HStack>
                        
                        {form.github_type === 'public' && (
                          <FormControl isRequired mb={4} isInvalid={!!errors.repo_url}>
                            <FormLabel>GitHub Repository URL</FormLabel>
                            <Input 
                              name="repo_url" 
                              placeholder="https://github.com/username/repository.git"
                              value={form.repo_url || ''}
                              onChange={(e) => {
                                const url = e.target.value;
                                handleChange(e);
                                
                                // Try to extract owner and repo from URL
                                try {
                                  if (url) {
                                    const urlObj = new URL(url);
                                    if (urlObj.hostname === 'github.com') {
                                      const pathParts = urlObj.pathname.split('/').filter(p => p);
                                      if (pathParts.length >= 2) {
                                        const owner = pathParts[0];
                                        let repo = pathParts[1];
                                        // Remove .git suffix if present
                                        if (repo.endsWith('.git')) {
                                          repo = repo.slice(0, -4);
                                        }
                                        
                                        setForm(prev => ({
                                          ...prev,
                                          owner: owner,
                                          repositories: repo
                                        }));
                                      }
                                    }
                                  }
                                } catch (error) {
                                  console.log("Error parsing URL:", error);
                                }
                              }}
                              bg="white"
                            />
                            <FormErrorMessage>{errors.repo_url}</FormErrorMessage>
                            <Text fontSize="xs" color="gray.600" mt={1}>
                              The full URL to the GitHub repository (e.g., https://github.com/username/repository.git)
                            </Text>
                          </FormControl>
                        )}
                        
                        {/* Enterprise GitHub Fields */}
                        {form.github_type === 'enterprise' && (
                          <FormControl isRequired isInvalid={!!errors.api_url} mb={4}>
                            <FormLabel>Enterprise GitHub URL</FormLabel>
                            <Input 
                              name="api_url" 
                              placeholder="https://github.yourdomain.com/api/v3"
                              value={form.api_url}
                              onChange={handleChange}
                              bg="white"
                            />
                            <FormErrorMessage>{errors.api_url}</FormErrorMessage>
                            <Text fontSize="xs" color="gray.600" mt={1}>
                              Your GitHub Enterprise URL with /api/v3 at the end
                            </Text>
                          </FormControl>
                        )}
                        
                        {/* Common Fields */}
                        <FormControl isRequired isInvalid={!!errors.token} mb={4}>
                          <FormLabel>Access Token</FormLabel>
                          <Input 
                            name="token" 
                            placeholder="GitHub Personal Access Token"
                            value={form.token}
                            onChange={handleChange}
                            type="password"
                            bg="white"
                          />
                          <FormErrorMessage>{errors.token}</FormErrorMessage>
                          <Text fontSize="xs" color="gray.600" mt={1}>
                            Required for API access - create at{" "}
                            <Link 
                              href={form.github_type === 'public' 
                                ? "https://github.com/settings/tokens" 
                                : "#"}
                              isExternal
                              color="blue.600"
                            >
                              {form.github_type === 'public' 
                                ? "github.com/settings/tokens" 
                                : "your enterprise instance"}
                            </Link>
                          </Text>
                        </FormControl>
                        
                        {/* Hidden field for owner - auto-populated from URL for public GitHub */}
                        {form.github_type === 'public' ? (
                          <Input type="hidden" name="owner" value={form.owner || ''} />
                        ) : (
                          <FormControl mb={4}>
                            <FormLabel>Enterprise Username</FormLabel>
                            <Input 
                              name="owner" 
                              placeholder="GitHub username"
                              value={form.owner}
                              onChange={handleChange}
                              bg="white"
                            />
                            <Text fontSize="xs" color="gray.600" mt={1}>
                              Username of the account that owns the repositories
                            </Text>
                          </FormControl>
                        )}
                        
                        <FormControl>
                          <FormLabel>Default Branch</FormLabel>
                          <Input 
                            name="default_branch" 
                            placeholder="main"
                            value={form.default_branch}
                            onChange={handleChange}
                            bg="white"
                          />
                          <Text fontSize="xs" color="gray.600" mt={1}>
                            Default branch name (usually 'main' or 'master')
                          </Text>
                        </FormControl>
                        
                        <FormControl mt={4}>
                          <FormLabel>SQL Tech Stack</FormLabel>
                          <Select
                            name="tech_stack"
                            value={form.tech_stack}
                            onChange={handleChange}
                            icon={<FaDatabase />}
                          >
                            <option value="postgresql">PostgreSQL</option>
                            <option value="mysql">MySQL</option>
                            <option value="snowflake">Snowflake</option>
                            <option value="tsql">T-SQL (SQL Server)</option>
                            <option value="dbt">DBT</option>
                          </Select>
                          <Text fontSize="xs" color="gray.600" mt={1}>
                            Select the SQL dialect used in this repository for optimal SQL parsing
                          </Text>
                        </FormControl>
                        
                        <FormControl display="flex" alignItems="center" mt={4}>
                          <FormLabel htmlFor="active" mb="0">
                            Active
                          </FormLabel>
                          <Switch 
                            id="active" 
                            name="active"
                            isChecked={form.active}
                            onChange={handleChange}
                            colorScheme="purple"
                          />
                        </FormControl>
                        
                        {renderTestResults()}
                        
                        <HStack spacing={4} justify="space-between">
                          <Button
                            leftIcon={<IoRefresh />}
                            onClick={testConnection}
                            colorScheme="blue"
                            isLoading={isTestingConnection}
                            loadingText="Testing"
                          >
                            Test Connection
                          </Button>
                          
                          <HStack>
                            <Button
                              onClick={resetForm}
                              variant="outline"
                            >
                              Cancel
                            </Button>
                            
                            <Button
                              type="submit"
                              colorScheme="purple"
                              isLoading={isSubmitting}
                              loadingText="Saving"
                              rightIcon={<IoCheckmark />}
                            >
                              {selectedConnector ? 'Update Connector' : 'Save Connector'}
                            </Button>
                          </HStack>
                        </HStack>
                      </Box>
                    </VStack>
                  </form>
                </CardBody>
              </Card>
            </Box>
          </TabPanel>
        </TabPanels>
      </Tabs>
      
      {/* Delete Confirmation Modal */}
      <Modal isOpen={isOpen} onClose={onClose} isCentered>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Confirm Deletion</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <Text>
              Are you sure you want to delete the GitHub connector "{selectedConnector?.name}"?
              This action cannot be undone.
            </Text>
          </ModalBody>
          <ModalFooter>
            <Button variant="outline" mr={3} onClick={onClose}>
              Cancel
            </Button>
            <Button colorScheme="red" onClick={handleDelete} leftIcon={<IoTrash />}>
              Delete
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
      
      {/* Vector Sync Modal */}
      <VectorSyncModal />
    </Container>
  );
};

export default GitHubConnectors; 