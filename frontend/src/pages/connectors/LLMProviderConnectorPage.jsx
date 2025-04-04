import React, { useState, useEffect } from 'react';
import {
  Box,
  Heading,
  Text,
  VStack,
  HStack,
  Input,
  Button,
  FormControl,
  FormLabel,
  FormHelperText,
  InputGroup,
  InputRightElement,
  Card,
  CardHeader,
  CardBody,
  CardFooter,
  Select,
  Divider,
  useToast,
  Icon,
  Accordion,
  AccordionItem,
  AccordionButton,
  AccordionPanel,
  AccordionIcon,
  Switch,
  Badge,
  SimpleGrid
} from '@chakra-ui/react';
import { IoCheckmarkCircle, IoCloseCircle, IoKeyOutline, IoLockClosed, IoRefresh, IoServer } from 'react-icons/io5';

const LLMProviderConnectorPage = () => {
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    openai: { api_key: '', base_url: '', organization: '', active: true },
    anthropic: { api_key: '', active: false },
    google: { api_key: '', active: false },
    huggingface: { api_key: '', active: false },
    ollama: { base_url: 'http://localhost:11434', active: false }
  });
  const [formKeys, setFormKeys] = useState({
    openai: { showApiKey: false },
    anthropic: { showApiKey: false },
    google: { showApiKey: false },
    huggingface: { showApiKey: false }
  });
  const toast = useToast();

  useEffect(() => {
    fetchProviders();
  }, []);

  const fetchProviders = async () => {
    setLoading(true);
    try {
      // Fetch provider configs from backend - using the correct path prefixed with /api
      console.log("Fetching provider data from /api/llm/providers...");
      const response = await fetch('/api/llm/providers');
      if (response.ok) {
        const data = await response.json();
        console.log("Fetched provider data:", data);
        setProviders(data.providers);
        
        // Update form data with fetched values
        const newFormData = { ...formData };
        data.configs.forEach(config => {
          if (newFormData[config.provider_id]) {
            // Check if the provider has a saved API key
            const hasApiKey = config.has_api_key === true;
            
            newFormData[config.provider_id] = {
              ...newFormData[config.provider_id],
              ...config,
              // Show masked API key if the provider has one saved
              api_key: hasApiKey ? '••••••••••••••••' : '',
              active: config.active
            };
          }
        });
        console.log("Updated form data:", newFormData);
        setFormData(newFormData);
      } else {
        toast({
          title: 'Error fetching providers',
          description: 'Could not fetch provider configurations',
          status: 'error',
          duration: 3000
        });
      }
    } catch (error) {
      console.error('Error fetching provider configs:', error);
      toast({
        title: 'Error',
        description: 'Failed to connect to the server',
        status: 'error',
        duration: 3000
      });
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (provider, field, value) => {
    setFormData(prev => ({
      ...prev,
      [provider]: {
        ...prev[provider],
        [field]: value
      }
    }));
  };

  const toggleShowApiKey = (provider) => {
    setFormKeys(prev => ({
      ...prev,
      [provider]: {
        ...prev[provider],
        showApiKey: !prev[provider].showApiKey
      }
    }));
  };

  const handleSubmit = async (provider) => {
    setSaving(true);
    try {
      // Don't send masked API keys to backend
      const dataToSend = { 
        ...formData[provider],
        provider_id: provider  // Explicitly ensure provider_id is included
      };
      
      if (dataToSend.api_key === '••••••••••••••••') {
        delete dataToSend.api_key;
      }

      console.log(`Sending data to API for ${provider}:`, JSON.stringify(dataToSend));

      const response = await fetch(`/api/llm/providers/${provider}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(dataToSend)
      });

      if (response.ok) {
        // If we've sent a new API key, update the form to show it as masked
        const hasApiKey = formData[provider].api_key && formData[provider].api_key !== '••••••••••••••••';
        
        if (hasApiKey) {
          // Update the form to show the API key as masked
          setFormData(prev => ({
            ...prev,
            [provider]: {
              ...prev[provider],
              api_key: '••••••••••••••••'
            }
          }));
        }

        toast({
          title: 'Configuration saved',
          description: `${provider.charAt(0).toUpperCase() + provider.slice(1)} configuration updated successfully`,
          status: 'success',
          duration: 3000
        });
        
        // Refresh provider data to get latest state
        fetchProviders();
      } else {
        const errorData = await response.json();
        console.error('Error response from server:', errorData);
        toast({
          title: 'Error saving configuration',
          description: errorData.detail || 'Failed to save configuration',
          status: 'error',
          duration: 3000
        });
      }
    } catch (error) {
      console.error(`Error saving ${provider} config:`, error);
      toast({
        title: 'Error',
        description: 'Failed to connect to the server',
        status: 'error',
        duration: 3000
      });
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async (provider) => {
    try {
      const response = await fetch(`/api/llm/providers/${provider}/test`, {
        method: 'POST'
      });

      if (response.ok) {
        const data = await response.json();
        toast({
          title: data.success ? 'Connection successful' : 'Connection failed',
          description: data.message,
          status: data.success ? 'success' : 'error',
          duration: 5000
        });
      } else {
        const errorData = await response.json();
        toast({
          title: 'Connection test failed',
          description: errorData.detail || 'Could not test connection',
          status: 'error',
          duration: 3000
        });
      }
    } catch (error) {
      console.error(`Error testing ${provider} connection:`, error);
      toast({
        title: 'Error',
        description: 'Failed to connect to the server',
        status: 'error',
        duration: 3000
      });
    }
  };

  const renderProviderConfig = (providerId, providerName, fields) => {
    const config = formData[providerId];
    if (!config) return null;

    // Check if the provider has an API key saved
    const hasApiKey = config.api_key === '••••••••••••••••' || config.has_api_key === true;

    return (
      <Card mb={4} variant="outline" borderColor="purple.200">
        <CardHeader bg="purple.50" borderBottom="1px" borderColor="purple.200">
          <HStack justifyContent="space-between">
            <Heading size="md">{providerName}</Heading>
            <HStack spacing={2}>
              {hasApiKey && fields.includes('api_key') && (
                <Badge colorScheme="green" display="flex" alignItems="center">
                  <Icon as={IoLockClosed} mr={1} />
                  API Key Saved
                </Badge>
              )}
              <Badge colorScheme={config.active ? "green" : "gray"}>
                {config.active ? "Active" : "Inactive"}
              </Badge>
            </HStack>
          </HStack>
        </CardHeader>
        <CardBody>
          <VStack spacing={4} align="stretch">
            <FormControl display="flex" alignItems="center">
              <FormLabel htmlFor={`${providerId}-active`} mb="0">
                Enable this provider
              </FormLabel>
              <Switch 
                id={`${providerId}-active`}
                isChecked={config.active} 
                onChange={(e) => handleInputChange(providerId, 'active', e.target.checked)}
                colorScheme="purple"
              />
            </FormControl>
            
            {fields.includes('api_key') && (
              <FormControl>
                <FormLabel>
                  API Key
                  {hasApiKey && (
                    <Badge ml={2} colorScheme="green" fontSize="xs">
                      Saved
                    </Badge>
                  )}
                </FormLabel>
                <InputGroup>
                  <Input
                    type={formKeys[providerId]?.showApiKey ? 'text' : 'password'}
                    value={config.api_key || ''}
                    onChange={(e) => handleInputChange(providerId, 'api_key', e.target.value)}
                    placeholder={hasApiKey ? "API key is saved" : `Enter ${providerName} API key`}
                    borderColor={hasApiKey ? "green.200" : undefined}
                    _hover={{ borderColor: hasApiKey ? "green.300" : undefined }}
                  />
                  <InputRightElement width="4.5rem">
                    <Button 
                      h="1.75rem" 
                      size="sm" 
                      onClick={() => toggleShowApiKey(providerId)}
                      isDisabled={config.api_key === ''}
                    >
                      {formKeys[providerId]?.showApiKey ? 'Hide' : 'Show'}
                    </Button>
                  </InputRightElement>
                </InputGroup>
                <FormHelperText>
                  {hasApiKey 
                    ? "Your API key is saved securely. Enter a new key to update it."
                    : `Your API key will be securely stored and used for ${providerName} API calls`
                  }
                </FormHelperText>
              </FormControl>
            )}
            
            {fields.includes('base_url') && (
              <FormControl>
                <FormLabel>Base URL</FormLabel>
                <Input
                  value={config.base_url || ''}
                  onChange={(e) => handleInputChange(providerId, 'base_url', e.target.value)}
                  placeholder={`${providerName} base URL`}
                />
                <FormHelperText>
                  {providerId === 'ollama' 
                    ? 'URL where your Ollama server is running' 
                    : 'Custom API endpoint (optional)'}
                </FormHelperText>
              </FormControl>
            )}
            
            {fields.includes('organization') && (
              <FormControl>
                <FormLabel>Organization ID</FormLabel>
                <Input
                  value={config.organization || ''}
                  onChange={(e) => handleInputChange(providerId, 'organization', e.target.value)}
                  placeholder="OpenAI organization ID"
                />
                <FormHelperText>
                  Optional organization ID for OpenAI team accounts
                </FormHelperText>
              </FormControl>
            )}
          </VStack>
        </CardBody>
        <CardFooter borderTop="1px" borderColor="purple.100" bg="gray.50">
          <HStack spacing={4}>
            <Button 
              colorScheme="purple" 
              onClick={() => handleSubmit(providerId)}
              isLoading={saving}
              loadingText="Saving"
            >
              Save Configuration
            </Button>
            {fields.includes('api_key') && (
              <Button 
                variant="outline" 
                colorScheme="blue" 
                onClick={() => testConnection(providerId)}
                isDisabled={!config.active || !hasApiKey}
                leftIcon={<Icon as={IoRefresh} />}
              >
                Test Connection
              </Button>
            )}
          </HStack>
        </CardFooter>
      </Card>
    );
  };

  return (
    <Box p={6}>
      <VStack spacing={6} align="stretch">
        <Box>
          <Heading size="lg" mb={2}>LLM Provider Configurations</Heading>
          <Text>Configure API keys and settings for different LLM providers</Text>
        </Box>
        
        <Divider />
        
        <SimpleGrid columns={{ base: 1, lg: 2 }} spacing={6}>
          {renderProviderConfig('openai', 'OpenAI', ['api_key', 'base_url', 'organization'])}
          {renderProviderConfig('anthropic', 'Anthropic', ['api_key'])}
          {renderProviderConfig('google', 'Google AI', ['api_key'])}
          {renderProviderConfig('huggingface', 'HuggingFace', ['api_key'])}
          {renderProviderConfig('ollama', 'Ollama', ['base_url'])}
        </SimpleGrid>
        
        <Box p={4} bg="blue.50" borderRadius="md">
          <HStack spacing={3}>
            <Icon as={IoKeyOutline} boxSize={6} color="blue.500" />
            <Box>
              <Heading size="sm">API Key Security</Heading>
              <Text fontSize="sm">
                All API keys are encrypted before being stored in the database. Your keys are never exposed in logs or server responses.
              </Text>
            </Box>
          </HStack>
        </Box>
      </VStack>
    </Box>
  );
};

export default LLMProviderConnectorPage; 