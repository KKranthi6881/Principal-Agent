import React from 'react';
import { Box, VStack, Heading, Link, Icon, Text, Divider, Stack, Accordion, AccordionItem, AccordionButton, AccordionPanel, AccordionIcon } from '@chakra-ui/react';
import { Link as RouterLink, useLocation } from 'react-router-dom';
import { IoHome, IoChatbox, IoSettings, IoServer, IoLogoGithub } from 'react-icons/io5';

const Sidebar = () => {
  const location = useLocation();
  const isActive = (path) => location.pathname === path;
  const isActiveStartsWith = (path) => location.pathname.startsWith(path);

  return (
    <Box 
      as="nav"
      h="100vh"
      w="240px"
      bg="white"
      boxShadow="0 4px 12px 0 rgba(0, 0, 0, 0.05)"
      position="fixed"
      left={0}
      top={0}
      p={4}
      overflowY="auto"
    >
      <VStack spacing={1} align="stretch">
        <Heading 
          size="md" 
          fontWeight="bold" 
          mb={6} 
          mt={2} 
          color="purple.700"
          textAlign="center"
        >
          Data Architect
        </Heading>
        
        <Link 
          as={RouterLink} 
          to="/" 
          p={3}
          borderRadius="md"
          bg={isActive('/') ? 'purple.50' : 'transparent'}
          color={isActive('/') ? 'purple.700' : 'gray.700'}
          fontWeight={isActive('/') ? 'bold' : 'normal'}
          _hover={{ 
            textDecoration: 'none', 
            bg: isActive('/') ? 'purple.50' : 'gray.100',
          }}
          display="flex"
          alignItems="center"
          mb={1}
        >
          <Icon as={IoHome} mr={3} />
          <Text>Home</Text>
        </Link>
        
        <Link 
          as={RouterLink} 
          to="/chat" 
          p={3}
          borderRadius="md"
          bg={isActiveStartsWith('/chat') ? 'purple.50' : 'transparent'}
          color={isActiveStartsWith('/chat') ? 'purple.700' : 'gray.700'}
          fontWeight={isActiveStartsWith('/chat') ? 'bold' : 'normal'}
          _hover={{ 
            textDecoration: 'none', 
            bg: isActiveStartsWith('/chat') ? 'purple.50' : 'gray.100',
          }}
          display="flex"
          alignItems="center"
          mb={1}
        >
          <Icon as={IoChatbox} mr={3} />
          <Text>Chat</Text>
        </Link>
        
        <Divider my={3} borderColor="gray.200" />
        
        <Heading 
          size="xs" 
          color="gray.500" 
          fontWeight="medium" 
          px={3} 
          mb={2}
        >
          CONNECTORS
        </Heading>
        
        <Link 
          as={RouterLink} 
          to="/connectors/llm" 
          p={3}
          borderRadius="md"
          bg={isActive('/connectors/llm') ? 'purple.50' : 'transparent'}
          color={isActive('/connectors/llm') ? 'purple.700' : 'gray.700'}
          fontWeight={isActive('/connectors/llm') ? 'bold' : 'normal'}
          _hover={{ 
            textDecoration: 'none', 
            bg: isActive('/connectors/llm') ? 'purple.50' : 'gray.100',
          }}
          display="flex"
          alignItems="center"
          mb={1}
        >
          <Icon as={IoServer} mr={3} />
          <Text>LLM Providers</Text>
        </Link>
        
        <Link 
          as={RouterLink} 
          to="/connectors/github" 
          p={3}
          borderRadius="md"
          bg={isActive('/connectors/github') ? 'purple.50' : 'transparent'}
          color={isActive('/connectors/github') ? 'purple.700' : 'gray.700'}
          fontWeight={isActive('/connectors/github') ? 'bold' : 'normal'}
          _hover={{ 
            textDecoration: 'none', 
            bg: isActive('/connectors/github') ? 'purple.50' : 'gray.100',
          }}
          display="flex"
          alignItems="center"
          mb={1}
        >
          <Icon as={IoLogoGithub} mr={3} />
          <Text>GitHub</Text>
        </Link>
      </VStack>
    </Box>
  );
};

export default Sidebar; 