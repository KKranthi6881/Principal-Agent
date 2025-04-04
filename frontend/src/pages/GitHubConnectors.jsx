import React, { useState, useEffect } from 'react';
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
  Icon
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
    repo_url: ''
  });
  
  // Form errors
  const [errors, setErrors] = useState({});
  
  // Fetch connectors on component mount
  useEffect(() => {
    fetchConnectors();
  }, []);
  
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
      
      const response = await fetch('/api/settings/github_connectors/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      });
      
      const data = await response.json();
      
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
      repo_url: ''
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
      repo_url: connector.repo_url || ''
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
  
  // Render list of existing connectors
  const renderConnectorsList = () => {
    if (isLoading) {
      return (
        <Box textAlign="center" py={10}>
          <Spinner size="xl" color="purple.500" />
          <Text mt={4}>Loading GitHub connectors...</Text>
        </Box>
      );
    }
    
    if (connectors.length === 0) {
      return (
        <Box textAlign="center" py={8} borderWidth="1px" borderRadius="lg" borderStyle="dashed">
          <Icon as={IoLogoGithub} w={10} h={10} color="gray.400" />
          <Text mt={4} color="gray.500">No GitHub connectors found</Text>
          <Text fontSize="sm" color="gray.400" mt={2}>Add a connector to integrate with GitHub repositories</Text>
        </Box>
      );
    }
    
    return (
      <VStack spacing={4} align="stretch">
        {connectors.map((connector) => (
          <Card key={connector.id} variant="outline">
            <CardHeader>
              <Flex justify="space-between" align="center">
                <HStack>
                  <Icon as={IoLogoGithub} w={6} h={6} color="purple.500" />
                  <Heading size="md">{connector.name}</Heading>
                  <Badge colorScheme={connector.active ? 'green' : 'gray'}>
                    {connector.active ? 'Active' : 'Inactive'}
                  </Badge>
                  <Badge colorScheme={connector.github_type === 'public' ? 'blue' : 'orange'}>
                    {connector.github_type === 'public' ? 'Public GitHub' : 'Enterprise GitHub'}
                  </Badge>
                </HStack>
                <HStack>
                  <Button 
                    size="sm" 
                    leftIcon={<IoSettings />} 
                    colorScheme="purple" 
                    variant="outline"
                    onClick={() => handleEdit(connector)}
                  >
                    Edit
                  </Button>
                  <Button 
                    size="sm" 
                    leftIcon={<IoTrash />} 
                    colorScheme="red" 
                    variant="outline"
                    onClick={() => confirmDelete(connector)}
                  >
                    Delete
                  </Button>
                </HStack>
              </Flex>
            </CardHeader>
            <CardBody pt={0}>
              {connector.description && (
                <Text mb={4} color="gray.600">{connector.description}</Text>
              )}
              
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <Box>
                  <Heading size="xs" mb={2}>Connection Details</Heading>
                  <List spacing={2}>
                    <ListItem>
                      <HStack>
                        <Icon as={IoPerson} color="gray.500" />
                        <Text fontWeight="bold" mr={1}>Owner:</Text>
                        <Text>{connector.owner || '-'}</Text>
                      </HStack>
                    </ListItem>
                    {connector.organization && (
                      <ListItem>
                        <HStack>
                          <Icon as={IoServer} color="gray.500" />
                          <Text fontWeight="bold" mr={1}>Organization:</Text>
                          <Text>{connector.organization}</Text>
                        </HStack>
                      </ListItem>
                    )}
                    {connector.github_type === 'enterprise' && connector.api_url && (
                      <ListItem>
                        <HStack>
                          <Icon as={IoLink} color="gray.500" />
                          <Text fontWeight="bold" mr={1}>API URL:</Text>
                          <Text>{connector.api_url}</Text>
                        </HStack>
                      </ListItem>
                    )}
                    <ListItem>
                      <HStack>
                        <Icon as={IoGitBranch} color="gray.500" />
                        <Text fontWeight="bold" mr={1}>Default Branch:</Text>
                        <Text>{connector.default_branch || 'main'}</Text>
                      </HStack>
                    </ListItem>
                    <ListItem>
                      <HStack>
                        <Icon as={IoLockClosed} color="gray.500" />
                        <Text fontWeight="bold" mr={1}>Token:</Text>
                        <Text>{connector.has_token ? '••••••••' : 'Not set'}</Text>
                      </HStack>
                    </ListItem>
                  </List>
                </Box>
                
                <Box>
                  <Heading size="xs" mb={2}>Repositories</Heading>
                  {connector.repositories && connector.repositories.length > 0 ? (
                    <Box maxH="120px" overflowY="auto" p={2} borderWidth="1px" borderRadius="md">
                      <List spacing={1}>
                        {connector.repositories.map((repo, index) => (
                          <ListItem key={index}>
                            <HStack>
                              <Icon as={IoCode} color="gray.500" />
                              <Text>{repo}</Text>
                            </HStack>
                          </ListItem>
                        ))}
                      </List>
                    </Box>
                  ) : (
                    <Text color="gray.500">No specific repositories configured</Text>
                  )}
                </Box>
              </SimpleGrid>
            </CardBody>
            <CardFooter pt={0}>
              <Text fontSize="sm" color="gray.500">
                Created: {new Date(connector.created_at).toLocaleString()}
                {connector.updated_at !== connector.created_at && 
                  ` • Updated: ${new Date(connector.updated_at).toLocaleString()}`}
              </Text>
            </CardFooter>
          </Card>
        ))}
      </VStack>
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
                      </Box>
                      
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
    </Container>
  );
};

export default GitHubConnectors; 