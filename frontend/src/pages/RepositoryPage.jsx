import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Grid,
  GridItem,
  Text,
  VStack,
  HStack,
  Icon,
  Input,
  InputGroup,
  InputLeftElement,
  Spinner,
  Button,
  Heading,
  Divider,
  Code,
  useToast,
  Flex,
  IconButton,
  Tooltip,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  Select
} from '@chakra-ui/react';
import { useLocation, useNavigate } from 'react-router-dom';
import { 
  IoSearch, 
  IoFolderOpen, 
  IoFolder,
  IoDocument, 
  IoChevronDown, 
  IoChevronForward,
  IoGitBranch,
  IoCode,
  IoPlayCircle,
  IoEye,
  IoShare,
  IoGitNetwork,
  IoApps,
  IoList,
  IoAnalytics,
  IoArrowBack,
  IoCheckmark
} from 'react-icons/io5';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { docco } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import { LineageGraph } from '../components/LineageGraph';

const RepositoryPage = () => {
  const [githubConnectors, setGithubConnectors] = useState([]);
  const [selectedConnector, setSelectedConnector] = useState(null);
  const [fileTree, setFileTree] = useState([]); 
  // Initialize expanded folders with root expanded by default
  const [expandedFolders, setExpandedFolders] = useState({root: true, '': true}); 
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [lineageData, setLineageData] = useState(null);
  const [showLineage, setShowLineage] = useState(false);
  // Track if initial tree has been expanded
  const [initialExpanded, setInitialExpanded] = useState(false);
  
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();

  // Fetch GitHub connectors on component mount
  useEffect(() => {
    fetchGithubConnectors();
    
    // Expand root level by default
    setExpandedFolders({root: true});
  }, []);

  // Fetch GitHub connectors from metadata.db via the API
  const fetchGithubConnectors = async () => {
    try {
      setLoading(true);
      // Using the correct API endpoint from the logs
      const response = await fetch('/api/settings/github_connectors');
      
      if (!response.ok) {
        throw new Error('Failed to fetch GitHub connectors');
      }
      
      const data = await response.json();
      // Adjust based on the actual response structure
      const connectors = data.connectors || data || [];
      setGithubConnectors(connectors);
      
      // If connectors are found, select the first one by default
      if (connectors.length > 0) {
        setSelectedConnector(connectors[0]);
        await fetchFileTree(connectors[0].repo_url);
        
        // Auto-expand all top-level directories after a short delay
        // to ensure fileTree is populated
        setTimeout(() => {
          const newExpandedState = { ...expandedFolders };
          fileTree.forEach(node => {
            if (node.type === 'dir' || node.isDirectory) {
              newExpandedState[node.path] = true;
            }
          });
          setExpandedFolders(newExpandedState);
          setInitialExpanded(true);
        }, 800);
      } else {
        // If no connectors are found, try to get repositories from syncs endpoint
        await fetchRepositoriesFromSyncs();
      }
    } catch (error) {
      console.error('Error fetching GitHub connectors:', error);
      // Fall back to syncs endpoint if connectors endpoint fails
      await fetchRepositoriesFromSyncs();
    } finally {
      setLoading(false);
    }
  };
  
  // Fallback method to fetch repositories from syncs endpoint
  const fetchRepositoriesFromSyncs = async () => {
    try {
      const response = await fetch('/api/github/syncs?limit=50');
      
      if (!response.ok) {
        throw new Error('Failed to fetch repositories from syncs');
      }
      
      const data = await response.json();
      // Convert syncs to a format compatible with our connectors
      const syncsAsConnectors = data.map(sync => ({
        id: sync.sync_id || sync.id,
        name: sync.repo_name || 'GitHub Repository',
        repo_url: sync.repo_url,
        default_branch: 'main',
        tech_stack: sync.tech_stack || 'unknown'
      }));
      
      setGithubConnectors(syncsAsConnectors);
      
      if (syncsAsConnectors.length > 0) {
        setSelectedConnector(syncsAsConnectors[0]);
        fetchFileTree(syncsAsConnectors[0].repo_url);
        
        // Also expand top-level folders by default
        setTimeout(() => expandAllTopLevelFolders(), 1000);
      }
    } catch (error) {
      console.error('Error fetching repositories from syncs:', error);
      toast({
        title: 'Error',
        description: 'Failed to fetch repositories. Please ensure you have GitHub repositories configured.',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  };

  // Function to handle connector selection change
  const handleConnectorChange = (connectorId) => {
    const connector = githubConnectors.find(c => c.id === connectorId);
    if (connector) {
      setSelectedConnector(connector);
      fetchFileTree(connector.repo_url);
    }
  };

  // Fetch file tree for a repository using connector
  const fetchFileTree = async (repoUrl) => {
    if (!repoUrl) return;
    try {
      setLoading(true);
      console.log('Fetching file tree for repo:', repoUrl);
      
      // Normalize the repo URL
      const normalizedUrl = normalizeGitHubUrl(repoUrl);
      console.log('Using normalized repo URL for file tree:', normalizedUrl);
      
      // Parse the URL to extract owner and repo components
      let owner, repo;
      try {
        // Extract owner/repo from URL
        const urlObj = new URL(normalizedUrl);
        const pathParts = urlObj.pathname.split('/');
        if (pathParts.length >= 3) {
          owner = pathParts[1];
          repo = pathParts[2].replace('.git', '');
          console.log(`Extracted owner=${owner}, repo=${repo} from URL`);
        }
      } catch (e) {
        console.error('Failed to parse repo URL:', e);
      }
      
      // Try multiple methods to get the file tree
      let success = false;
      
      // 1. First try using owner and repo parameters if we parsed them successfully
      if (owner && repo) {
        console.log(`Attempting to fetch file tree using owner=${owner} and repo=${repo} parameters`);
        const ownerRepoResponse = await fetch(`/api/github/files?owner=${encodeURIComponent(owner)}&repo=${encodeURIComponent(repo)}`);
        
        if (ownerRepoResponse.ok) {
          console.log('Successfully fetched file tree using owner/repo parameters');
          success = await handleFilesResponse(ownerRepoResponse);
          if (success) {
            setLoading(false);
            return;
          }
        } else {
          console.log(`Failed to fetch file tree using owner/repo: ${ownerRepoResponse.status} ${ownerRepoResponse.statusText}`);
        }
      }
      
      // 2. Try using sync data as a fallback
      const syncResponse = await fetchFilesFromSyncs(normalizedUrl);
      if (syncResponse) {
        console.log('Successfully fetched file tree from syncs data');
        setLoading(false);
        return;
      }
      
      // 2. Fall back to direct GitHub API if the above fails
      const githubApiResponse = await fetch(`/api/github/files?owner=${owner}&repo=${repo}`);
      
      if (githubApiResponse.ok) {
        console.log('Fetched file tree successfully using GitHub API');
        const success = await handleFilesResponse(githubApiResponse);
        if (success) {
          setLoading(false);
          return;
        }
      } else {
        console.log(`Failed to fetch file tree using GitHub API: ${response.status} ${response.statusText}`);
      }
      
      // If all methods fail, show an error
      throw new Error('Failed to fetch file tree');
    } catch (error) {
      console.error('Error fetching file tree:', error);
      toast({
        title: 'Error',
        description: `Failed to fetch file tree: ${error.message}`,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
      setFileTree([]);
    } finally {
      setLoading(false);
    }
  };
  
  // Parse the GitHub API response data
  const handleFilesResponse = async (response) => {
    try {
      const data = await response.json();
      console.log('GitHub API response:', data);
      
      // Ensure we have an array of files
      const filesArray = Array.isArray(data) ? data : 
                      (data.files ? data.files : 
                      (data.tree ? data.tree.map(item => ({
                        path: item.path,
                        type: item.type === 'blob' ? 'file' : 'dir',
                        is_dir: item.type === 'tree'
                      })) : []));
      
      console.log('Processed files array:', filesArray);
      const tree = buildFileTree(filesArray);
      setFileTree(tree);
      
      // Auto-expand top-level folders
      setTimeout(() => {
        expandAllTopLevelFolders();
      }, 300);
      
      return true;
    } catch (error) {
      console.error('Error parsing GitHub files response:', error);
      return false;
    }
  };

  // Build a hierarchical file tree from flat list
  const buildFileTree = (files) => {
    console.log("Building file tree from data:", files);
    
    // Make sure we're working with an array
    if (!Array.isArray(files)) {
      console.error("Expected array of files but got:", typeof files);
      return [];
    }
    
    const tree = [];
    const paths = {};

    // Filter out any null or undefined entries
    const validFiles = files.filter(f => f && f.path);
    console.log("Valid files:", validFiles.length);
    
    // Sort files to ensure folders come before files
    validFiles.sort((a, b) => {
      const aIsDir = a.type === 'dir' || a.is_dir === true || a.path.endsWith('/');
      const bIsDir = b.type === 'dir' || b.is_dir === true || b.path.endsWith('/');
      if (aIsDir && !bIsDir) return -1;
      if (!aIsDir && bIsDir) return 1;
      return a.path.localeCompare(b.path);
    });

    // Create a map of all paths to ensure we don't miss any directories
    const allPaths = new Set();
    
    // Log input data sample
    if (validFiles.length > 0) {
      console.log("Sample file entry:", validFiles[0]);
    }
    
    // First gather all explicit paths
    validFiles.forEach(file => {
      const path = file.path;
      allPaths.add(path);
      
      // Also add all parent directory paths
      const parts = path.split('/');
      for (let i = 1; i < parts.length; i++) {
        const parentPath = parts.slice(0, i).join('/');
        allPaths.add(parentPath + '/');
      }
    });
    
    // Now create nodes for all paths
    Array.from(allPaths).forEach(path => {
      const isDirectory = path.endsWith('/') || validFiles.find(f => f.path === path)?.type === 'dir';
      const cleanPath = isDirectory ? path.replace(/\/$/, '') : path;
      const parts = cleanPath.split('/');
      const name = parts[parts.length - 1] || cleanPath;
      
      // Skip if already created
      if (paths[cleanPath]) return;
      
      const node = {
        name,
        path: path,
        type: isDirectory ? 'dir' : 'file',
        children: isDirectory ? [] : null,
        parent: parts.length > 1 ? parts.slice(0, -1).join('/') : null,
      };
      
      paths[cleanPath] = node;
      
      // If it's a root-level item, add to the tree
      if (parts.length === 1 || !parts[0]) {
        tree.push(node);
      }
    });

    // Second pass: connect children to parents
    Object.values(paths).forEach(node => {
      if (node.parent) {
        // Ensure parent exists (create if needed)
        if (!paths[node.parent]) {
          const parts = node.parent.split('/');
          const parentName = parts[parts.length - 1] || node.parent;
          
          paths[node.parent] = {
            name: parentName,
            path: node.parent + '/',
            type: 'dir',
            children: [],
            parent: parts.length > 1 ? parts.slice(0, -1).join('/') : null,
          };
          
          // If this is a top-level parent, add to tree
          if (parts.length === 1 || !parts[0]) {
            tree.push(paths[node.parent]);
          }
        }
        
        // Add this node as a child of its parent
        const parent = paths[node.parent];
        parent.children = parent.children || [];
        
        // Avoid duplicates
        if (!parent.children.some(child => child.path === node.path)) {
          parent.children.push(node);
        }
      }
    });

    // Sort children within each node
    const sortChildren = (node) => {
      if (node.children && node.children.length) {
        node.children.sort((a, b) => {
          // Directories first, then alphabetically
          if (a.type === 'dir' && b.type !== 'dir') return -1;
          if (a.type !== 'dir' && b.type === 'dir') return 1;
          return a.name.localeCompare(b.name);
        });
        
        // Recursively sort children's children
        node.children.forEach(sortChildren);
      }
    };
    
    // Sort top-level items
    tree.sort((a, b) => {
      if (a.type === 'dir' && b.type !== 'dir') return -1;
      if (a.type !== 'dir' && b.type === 'dir') return 1;
      return a.name.localeCompare(b.name);
    });
    
    // Sort all children recursively
    tree.forEach(sortChildren);
    
    return tree;
  };

  // Helper function to normalize GitHub URLs
  const normalizeGitHubUrl = (url) => {
    // If it already contains github.com, make sure it's not duplicated
    if (url.includes('github.com')) {
      // Check for duplicated github.com
      if (url.includes('github.com/github.com')) {
        return url.replace('github.com/github.com', 'github.com');
      }
      
      // Check if it's a full URL with https://
      if (url.startsWith('https://')) {
        return url;
      }
      
      // If it's just owner/repo format, add the https prefix
      if (!url.startsWith('http')) {
        return `https://github.com/${url}`;
      }
    }
    
    return url;
  };

  // Fetch file content from the GitHub API
  const fetchFileContent = async (repo, path) => {
    if (!repo || !path) return;
    try {
      setLoading(true);
      
      // Check if the selected file is a directory
      if (selectedFile && selectedFile.type === 'dir') {
        setFileContent('');
        setLineageData(null);
        setLoading(false);
        return;
      }
      
      console.log(`Fetching content for file: ${path} from repo: ${repo}`);
      
      // Use the normalized repo URL to fetch content
      const normalizedRepo = normalizeGitHubUrl(repo);
      const response = await fetch(`/api/github/content?repo=${encodeURIComponent(normalizedRepo)}&path=${encodeURIComponent(path)}`);
      
      if (!response.ok) {
        throw new Error(`Failed to fetch file content: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      setFileContent(data.content || '');
      
      // For SQL files, try to fetch lineage data
      const fileExtension = getFileExtension(path);
      if (['sql', 'yml', 'yaml'].includes(fileExtension)) {
        // Fetch lineage data if it's a SQL or YAML file
        fetchLineageData(repo, path);
      } else {
        setLineageData(null);
        setShowLineage(false);
      }
    } catch (error) {
      console.error('Error fetching file content:', error);
      setFileContent(`// Error fetching file content: ${error.message}`);
      toast({
        title: 'Error',
        description: `Failed to fetch file content: ${error.message}`,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setLoading(false);
    }
  };
  
  // Fetch lineage data for the selected file
  const fetchLineageData = async (repo, path) => {
    if (!repo || !path) return;
    try {
      // Normalize the repo URL first
      const normalizedRepo = normalizeGitHubUrl(repo);
      
      // Create a github_path in the format: owner/repo/path
      let githubPath;
      try {
        // Handle both URL format and owner/repo format
        if (normalizedRepo.startsWith('http')) {
          const repoUrl = new URL(normalizedRepo);
          // Extract owner/repo from URL path (remove leading slash)
          const repoPath = repoUrl.pathname.substring(1);
          githubPath = `${repoPath}/${path}`;
        } else {
          // If already in owner/repo format
          githubPath = `${normalizedRepo}/${path}`;
        }
        
        // Remove .git suffix if present
        githubPath = githubPath.replace(/\.git\//, '/');
      } catch (error) {
        console.error('Error parsing repo URL:', error);
        // Fallback to simple concatenation
        githubPath = `${repo.replace(/\/$/, '')}/${path}`;
      }
      
      console.log('Fetching lineage for path:', githubPath);
      const response = await fetch(`/api/lineage/by-path?github_path=${encodeURIComponent(githubPath)}`);
      
      if (!response.ok) {
        if (response.status === 404) {
          // No lineage data available, this is not an error
          console.log('No lineage data available for this file');
          setLineageData(null);
          setShowLineage(false);
          return;
        }
        throw new Error(`Failed to fetch lineage data: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log('Lineage API response:', data);
      
      if (data && data.success && data.lineage_json) {
        console.log('Lineage data received:', data.lineage_json);
        // Transform the data for the LineageGraph component
        const transformedData = transformLineageData(data.lineage_json);
        
        if (transformedData) {
          setLineageData(transformedData);
          toast({
            title: 'Lineage Data Available',
            description: 'Click the "Show Lineage" button to visualize data relationships',
            status: 'info',
            duration: 3000,
            isClosable: true,
          });
        } else {
          // We got data but it didn't transform correctly
          setLineageData(null);
          setShowLineage(false);
          toast({
            title: 'Lineage Visualization Error',
            description: 'Could not create valid lineage visualization from the data',
            status: 'warning',
            duration: 3000,
            isClosable: true,
          });
        }
      } else {
        setLineageData(null);
        setShowLineage(false);
        toast({
          title: 'No Lineage Data Available',
          description: data?.message || 'No lineage data found for this file',
          status: 'info',
          duration: 3000,
          isClosable: true,
        });
      }
    } catch (error) {
      console.error('Error fetching lineage data:', error);
      setLineageData(null);
      setShowLineage(false);
      toast({
        title: 'Error',
        description: `Failed to fetch lineage data: ${error.message}`,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  };

  // Transform lineage data to format expected by LineageGraph
  const transformLineageData = (lineageJson) => {
    console.log('Transforming lineage data with keys:', Object.keys(lineageJson));
    
    try {
      // First, add the root table to make sure it's included
      const allTables = [...(Array.isArray(lineageJson.tables) ? lineageJson.tables : [])];
      
      // Add root table if it's not already in the tables array
      if (lineageJson.root_table && !allTables.some(t => t.id === lineageJson.root_table.id)) {
        allTables.push(lineageJson.root_table);
      }
      
      // Log the table information for debugging
      console.log('Root table:', lineageJson.root_table);
      console.log('All tables count:', allTables.length);
      console.log('Sample tables:', allTables.slice(0, 3));
      
      // If we don't have any tables, create at least one for the root
      if (allTables.length === 0 && lineageJson.root_table) {
        allTables.push({
          id: 'root-table',
          name: lineageJson.root_table.name || 'Root Table',
          github_path: lineageJson.root_table.github_path || '',
          tech_stack: lineageJson.root_table.tech_stack || 'unknown',
        });
      }
      
      // Transform tables to models (safely handle missing data)
      const models = allTables.map(table => ({
        id: table.id || `table-${Math.random().toString(36).substring(2, 9)}`,
        name: table.name || 'Unknown',
        path: table.github_path || '',
        type: table.tech_stack || 'unknown',
        highlight: lineageJson.root_table && table.id === lineageJson.root_table.id
      }));
      
      // Create a set of valid model IDs to filter edges
      const modelIds = new Set(models.map(model => model.id));
      console.log('Valid model IDs count:', modelIds.size);
      
      // If we have relationships, use them; otherwise create a simple self-referential edge
      let edges = [];
      
      if (Array.isArray(lineageJson.relationships) && lineageJson.relationships.length > 0) {
        // Log relationships for debugging
        console.log('Relationships count:', lineageJson.relationships.length);
        console.log('Sample relationship:', lineageJson.relationships[0]);
        
        // Transform relationships to edges (safely handle missing data)
        edges = lineageJson.relationships
          .filter(rel => {
            // Only include relationships where both source and target tables exist in our models
            return rel.source && rel.target && 
                  rel.source.table_id && rel.target.table_id && 
                  modelIds.has(rel.source.table_id) && modelIds.has(rel.target.table_id);
          })
          .map(rel => ({
            id: rel.id || `edge-${Math.random().toString(36).substring(2, 9)}`,
            source: rel.source.table_id, // Changed from 'from' to 'source'
            target: rel.target.table_id, // Changed from 'to' to 'target'
            type: rel.type || 'depends_on'
          }));
      } else if (models.length > 0) {
        // Create at least one edge if we have models but no relationships
        // This ensures we have something to display
        if (models.length === 1) {
          // Self-reference for single model
          edges = [{
            id: 'self-edge',
            source: models[0].id, // Changed from 'from' to 'source'
            target: models[0].id, // Changed from 'to' to 'target'
            type: 'self'
          }];
        } else if (models.length > 1) {
          // Connect first two models
          edges = [{
            id: 'default-edge',
            source: models[0].id, // Changed from 'from' to 'source'
            target: models[1].id, // Changed from 'to' to 'target'
            type: 'depends_on'
          }];
        }
      }
      
      // Transform columns if they exist and belong to valid models
      const columns = Array.isArray(lineageJson.columns) ? lineageJson.columns
        .filter(col => col.table_id && modelIds.has(col.table_id))
        .map(col => ({
          id: col.id || `col-${Math.random().toString(36).substring(2, 9)}`,
          name: col.name || 'Unknown',
          modelId: col.table_id,
          dataType: col.data_type || 'unknown',
          type: col.is_primary_key ? 'primary_key' : col.is_foreign_key ? 'foreign_key' : 'regular'
        })) : [];
      
      // Create a set of valid column IDs for filtering column connections
      const columnIds = new Set(columns.map(col => col.id));
      
      // Column lineage connections if they exist
      const columnConnections = Array.isArray(lineageJson.relationships) ? 
        lineageJson.relationships
          .filter(rel => {
            return rel.source?.column_id && rel.target?.column_id && 
                  columnIds.has(rel.source.column_id) && columnIds.has(rel.target.column_id);
          })
          .map(rel => ({
            id: `col_${rel.id || Math.random().toString(36).substring(2, 9)}`,
            fromColumn: rel.source.column_id,
            toColumn: rel.target.column_id,
            type: rel.type || 'depends_on'
          })) : [];
      
      // Validate that we have valid models and edges
      const validData = models.length > 0 && edges.length > 0;
      
      console.log('Transformed data:', {
        models: models.length,
        edges: edges.length,
        columns: columns.length,
        column_lineage: columnConnections.length,
        valid: validData
      });
      
      if (!validData) {
        console.error('Invalid lineage data: insufficient valid models or edges');
        return null;
      }
      
      // Always return at least this minimum structure
      return {
        models,
        edges,
        columns,
        column_lineage: columnConnections
      };
    } catch (error) {
      console.error('Error transforming lineage data:', error);
      return null;
    }
  };

  // Toggle folder expansion with additional debug
  const toggleFolder = (path) => {
    console.log('Toggling folder:', path);
    
    // Get the node from the file tree
    let node = findNodeByPath(fileTree, path);
    if (node) {
      console.log(`Found node ${path} with ${node.children ? node.children.length : 0} children`);
      // Log all children to help debug
      if (node.children) {
        console.log('Children paths:', node.children.map(c => c.path));
      }
    } else {
      console.log(`Node ${path} not found in file tree`);
    }
    
    // Toggle expansion state
    setExpandedFolders(prev => {
      const newState = {
        ...prev,
        [path]: !prev[path]
      };
      console.log('New expanded state:', newState);
      return newState;
    });
    
    // If we're expanding a folder that has no children or isn't expanded yet,
    // try to fetch its contents specifically
    if (node && (!node.children || node.children.length === 0) && !expandedFolders[path]) {
      console.log('Fetching contents for folder:', path);
      if (selectedConnector && selectedConnector.repo_url) {
        fetchFolderContents(selectedConnector.repo_url, path);
      }
    }
  };
  
  // Helper to find a node in the tree by path
  const findNodeByPath = (nodes, path) => {
    if (!nodes) return null;
    
    for (const node of nodes) {
      if (node.path === path) {
        return node;
      }
      if (node.children) {
        const found = findNodeByPath(node.children, path);
        if (found) return found;
      }
    }
    return null;
  };
  
  // Fetch contents specifically for a folder
  const fetchFolderContents = async (repoUrl, folderPath) => {
    if (!repoUrl || !folderPath) return;
    
    try {
      console.log(`Fetching contents for folder: ${folderPath} in repo: ${repoUrl}`);
      
      // Parse the URL to extract owner and repo
      let owner, repo;
      try {
        const urlObj = new URL(normalizeGitHubUrl(repoUrl));
        const pathParts = urlObj.pathname.split('/');
        if (pathParts.length >= 3) {
          owner = pathParts[1];
          repo = pathParts[2].replace('.git', '');
        }
      } catch (e) {
        console.error('Failed to parse repo URL:', e);
        return;
      }
      
      // Fetch folder contents
      if (owner && repo) {
        // Clean up the folder path (remove leading/trailing slashes)
        const cleanPath = folderPath.replace(/^\/+|\/+$/g, '');
        
        const response = await fetch(
          `/api/github/files?owner=${encodeURIComponent(owner)}&repo=${encodeURIComponent(repo)}&path=${encodeURIComponent(cleanPath)}`
        );
        
        if (!response.ok) {
          console.error(`Failed to fetch folder contents: ${response.status} ${response.statusText}`);
          return;
        }
        
        const files = await response.json();
        console.log(`Fetched ${files.length} files for folder ${folderPath}:`, files);
        
        // Update the file tree with the fetched contents
        updateFileTreeWithFolderContents(folderPath, files);
      }
    } catch (error) {
      console.error('Error fetching folder contents:', error);
    }
  };
  
  // Update the file tree with fetched folder contents
  const updateFileTreeWithFolderContents = (folderPath, files) => {
    // Don't update if no files found
    if (!files || files.length === 0) return;
    
    setFileTree(prevTree => {
      // Create a deep copy of the tree
      const newTree = JSON.parse(JSON.stringify(prevTree));
      
      // Find the folder node to update
      const updateNodeChildren = (nodes, path) => {
        for (let i = 0; i < nodes.length; i++) {
          const node = nodes[i];
          
          if (node.path === path || node.path === path + '/') {
            // Found the folder, update its children
            console.log(`Updating children for ${path} with ${files.length} files`);
            
            // Create folder children based on the fetched files
            node.children = files.map(file => {
              const isDir = file.is_dir || file.type === 'dir';
              const filePath = file.path;
              const fileName = filePath.split('/').pop() || filePath;
              
              return {
                name: fileName,
                path: filePath,
                type: isDir ? 'dir' : 'file',
                isDirectory: isDir,
                children: isDir ? [] : null,
                parent: folderPath
              };
            });
            
            // Sort children (folders first, then alphabetically)
            node.children.sort((a, b) => {
              if ((a.type === 'dir') !== (b.type === 'dir')) {
                return a.type === 'dir' ? -1 : 1;
              }
              return a.name.localeCompare(b.name);
            });
            
            return true;
          } else if (node.children && node.children.length > 0) {
            // Recursively search in children
            if (updateNodeChildren(node.children, path)) {
              return true;
            }
          }
        }
        return false;
      };
      
      // Try to update the folder in the tree
      if (!updateNodeChildren(newTree, folderPath)) {
        console.error(`Couldn't find folder ${folderPath} in the file tree to update`);
      }
      
      return newTree;
    });
  };

  // Check if a folder is expanded
  const isFolderExpanded = (path) => {
    // Root is expanded by default
    if (path === '' || path === '/') {
      return true;
    }
    return expandedFolders[path] === true;
  };
  
  // Expand all parent folders of a path
  const expandParentFolders = (path) => {
    const parts = path.split('/');
    let currentPath = '';
    
    setExpandedFolders(prev => {
      const newState = {...prev};
      
      // For each segment in the path, expand its parent folder
      for (let i = 0; i < parts.length - 1; i++) {
        if (currentPath) {
          currentPath += '/';
        }
        currentPath += parts[i];
        newState[currentPath] = true;
      }
      
      return newState;
    });
  };
  
  // Helper function to expand all top-level folders
  const expandAllTopLevelFolders = () => {
    const newExpandedState = { ...expandedFolders };
    
    // Always expand root and empty path
    newExpandedState['root'] = true;
    newExpandedState[''] = true;
    newExpandedState['/'] = true;
    
    console.log('File tree for expansion:', fileTree);
    
    // Expand all top-level folders and their immediate children
    if (fileTree && fileTree.length > 0) {
      fileTree.forEach(node => {
        if (!node) return;
        
        if (node.type === 'dir' || node.isDirectory === true) {
          console.log('Expanding top-level folder:', node.path);
          newExpandedState[node.path] = true;
          
          // Also expand first level children
          if (node.children && node.children.length > 0) {
            node.children.forEach(child => {
              if (!child) return;
              
              if (child.type === 'dir' || child.isDirectory === true) {
                console.log('Expanding second-level folder:', child.path);
                newExpandedState[child.path] = true;
              }
            });
          }
        }
      });
    }
    
    console.log('Expanding all top-level folders:', newExpandedState);
    setExpandedFolders(newExpandedState);
  };

  // Render file tree recursively
  const renderFileTree = (nodes, depth = 0) => {
    if (!nodes) {
      console.log(`No nodes provided at depth ${depth}`);
      return <Text color="gray.500" pl={depth > 0 ? 4 : 0}>No files found</Text>;
    }
    
    if (nodes.length === 0) {
      console.log(`Empty nodes array at depth ${depth}`);
      return <Text color="gray.500" pl={depth > 0 ? 4 : 0}>No files found</Text>;
    }

    // Filter nodes based on search query if one exists
    let filteredNodes = nodes;
    
    if (searchQuery) {
      const lowerQuery = searchQuery.toLowerCase();
      filteredNodes = nodes.filter(node => {
        // Show if the name matches or if it's a parent directory of a matching file
        const nameMatch = node.name.toLowerCase().includes(lowerQuery);
        const childrenMatch = node.children && searchInChildren(node.children, lowerQuery);
        return nameMatch || childrenMatch;
      });
      
      // If searching, automatically expand all folders that contain matches
      if (filteredNodes.length > 0) {
        // Create a single new state object instead of multiple updates
        const newExpandedState = { ...expandedFolders };
        
        // Track all folders to expand
        const expandAllFolders = (nodes) => {
          if (!nodes) return;
          
          nodes.forEach(node => {
            if (node.type === 'dir' || node.isDirectory) {
              newExpandedState[node.path] = true;
              if (node.children) {
                expandAllFolders(node.children);
              }
            }
          });
        };
        
        expandAllFolders(filteredNodes);
        setExpandedFolders(newExpandedState);
      }
    }
    
    // Log the nodes being rendered for debugging
    console.log(`Rendering ${filteredNodes.length} nodes at depth ${depth}:`, 
      filteredNodes.map(n => n.path));
    
    // Helper function to search in children recursively
    function searchInChildren(children, query) {
      if (!children) return false;
      
      return children.some(child => {
        const nameMatch = child.name.toLowerCase().includes(query);
        const childrenMatch = child.children && searchInChildren(child.children, query);
        return nameMatch || childrenMatch;
      });
    }

    return (
      <VStack align="stretch" spacing={0} pl={depth > 0 ? 4 : 0}>
        {filteredNodes.map((node, index) => {
          if (!node) {
            console.error(`Undefined node at index ${index}`);
            return null;
          }
          
          const isExpanded = isFolderExpanded(node.path);
          const isDirectory = node.type === 'dir' || node.isDirectory === true;
          const isSelected = selectedFile && selectedFile.path === node.path;
          const nodeName = node.name || node.path.split('/').pop() || node.path;
          
          // Debug info
          if (isDirectory) {
            if (node.children) {
              console.log(`Folder ${node.path} has ${node.children.length} children, expanded: ${isExpanded}`);
            } else {
              console.log(`Folder ${node.path} has no children array defined`);
            }
          }
          
          return (
            <Box key={`${node.path}-${index}`}>
              <HStack 
                p={2}
                spacing={2}
                cursor="pointer"
                backgroundColor={isSelected ? 'blue.50' : 'transparent'}
                _hover={{ backgroundColor: isSelected ? 'blue.100' : 'gray.100' }}
                onClick={() => {
                  if (isDirectory) {
                    console.log('Clicked directory:', node.path);
                    
                    // Update selected file to the directory
                    setSelectedFile({
                      ...node,
                      path: node.path,
                      name: nodeName,
                      type: 'dir',
                      isDirectory: true
                    });
                    
                    // Toggle folder expansion after updating selected file
                    toggleFolder(node.path);
                  } else {
                    console.log('Clicked file:', node.path);
                    if (selectedConnector && selectedConnector.repo_url) {
                      // Pass both repo URL and file path to the fetchFileContent function
                      fetchFileContent(selectedConnector.repo_url, node.path);
                      // Update selectedFile with more properties
                      setSelectedFile({
                        ...node,
                        path: node.path,
                        name: nodeName,
                        type: 'file',
                        isDirectory: false
                      });
                      
                      // Expand all parent folders of the selected file
                      expandParentFolders(node.path);
                    } else {
                      toast({
                        title: 'Error',
                        description: 'No repository selected',
                        status: 'error',
                        duration: 3000,
                        isClosable: true,
                      });
                    }
                  }
                }}
                bg={isSelected ? 'blue.50' : 'transparent'}
                borderRadius="md"
              >
                {/* Selection indicator */}
                {isDirectory && (
                  <Icon 
                    as={isExpanded ? IoChevronDown : IoChevronForward} 
                    color="gray.500" 
                    boxSize={4}
                  />
                )}
                
                <Icon 
                  as={isDirectory 
                    ? (isExpanded ? IoFolderOpen : IoFolder) 
                    : getFileIcon(node.name)} 
                  color={isDirectory 
                    ? 'blue.500' 
                    : getFileColor(node.name)} 
                  boxSize={4}
                />
                
                <Text fontSize="sm" noOfLines={1} fontWeight={isSelected ? "bold" : "normal"}>
                  {nodeName}
                </Text>
                
                {/* Add lineage icon for SQL and YAML files */}
                {!isDirectory && ['sql', 'yml', 'yaml'].includes(getFileExtension(nodeName)) && (
                  <Tooltip label="View data lineage">
                    <IconButton
                      icon={<Icon as={IoGitNetwork} />}
                      size="xs"
                      variant="ghost"
                      colorScheme="blue"
                      ml="auto"
                      onClick={(e) => {
                        e.stopPropagation(); // Prevent triggering the parent click handler
                        if (selectedConnector) {
                          // First select the file to ensure content is loaded
                          fetchFileContent(selectedConnector.repo_url, node.path);
                          setSelectedFile({
                            ...node,
                            path: node.path,
                            name: nodeName,
                            type: 'file'
                          });
                          
                          // Then fetch lineage data and show it
                          fetchLineageData(selectedConnector.repo_url, node.path);
                          setShowLineage(true);
                        }
                      }}
                      aria-label="View lineage"
                    />
                  </Tooltip>
                )}
                
                {/* Add lineage icon for SQL and YAML files */}
                {!isDirectory && ['sql', 'yml', 'yaml'].includes(getFileExtension(nodeName)) && (
                  <Tooltip label="View data lineage">
                    <IconButton
                      icon={<Icon as={IoGitNetwork} />}
                      size="xs"
                      variant="ghost"
                      colorScheme="blue"
                      ml="auto"
                      onClick={(e) => {
                        e.stopPropagation(); // Prevent triggering the parent click handler
                        if (selectedConnector) {
                          // First select the file to ensure content is loaded
                          fetchFileContent(selectedConnector.repo_url, node.path);
                          setSelectedFile({
                            ...node,
                            path: node.path,
                            name: nodeName,
                            type: 'file'
                          });
                          
                          // Then fetch lineage data if available
                          fetchLineageData(selectedConnector.repo_url, node.path)
                            .then(() => {
                              // Show lineage visualization
                              setShowLineage(true);
                            });
                        }
                      }}
                      aria-label="View lineage"
                    />
                  </Tooltip>
                )}
              </HStack>
              
              {/* If directory is expanded and has children, show them */}
              {isDirectory && isExpanded && (
                <Box pl={4} borderLeft="1px" borderColor="gray.200" ml={2} mt={1}>
                  {node.children && node.children.length > 0 
                    ? renderFileTree(node.children, depth + 1)
                    : <Text pl={4} py={2} color="gray.500" fontSize="sm">Empty folder</Text>
                  }
                </Box>
              )}
            </Box>
          );
        })}
      </VStack>
    );
  };

  // Get file extension for syntax highlighting
  const getFileExtension = (filePath) => {
    if (!filePath) return 'text';
    const ext = filePath.split('.').pop().toLowerCase();
    
    const extensionMap = {
      'js': 'javascript',
      'jsx': 'jsx',
      'py': 'python',
      'sql': 'sql',
      'json': 'json',
      'html': 'html',
      'css': 'css',
      'md': 'markdown',
      'yml': 'yaml',
      'yaml': 'yaml',
      'txt': 'text',
      'sh': 'bash',
      'bash': 'bash',
      'csv': 'text',
      'tsv': 'text',
    };
    
    return extensionMap[ext] || 'text';
  };
  
  // Get icon based on file type 
  const getFileIcon = (fileName) => {
    if (!fileName) return IoDocument;
    
    const ext = fileName.split('.').pop().toLowerCase();
    
    // Map file extensions to appropriate icons
    const iconMap = {
      'sql': IoCode,
      'yml': IoList,
      'yaml': IoList,
      'md': IoDocument,
      'json': IoCode,
      'py': IoCode,
      'js': IoCode,
      'jsx': IoCode,
      'html': IoCode,
      'css': IoCode,
      'txt': IoDocument,
      'csv': IoList,
      'tsv': IoList,
    };
    
    return iconMap[ext] || IoDocument;
  };
  
  // Get color based on file type
  const getFileColor = (fileName) => {
    if (!fileName) return 'gray.500';
    
    const ext = fileName.split('.').pop().toLowerCase();
    
    // Map file extensions to appropriate colors
    const colorMap = {
      'sql': 'green.600',
      'yml': 'purple.500',
      'yaml': 'purple.500',
      'md': 'gray.500',
      'json': 'orange.500',
      'py': 'blue.600',
      'js': 'yellow.600',
      'jsx': 'yellow.600',
      'html': 'red.500',
      'css': 'pink.500',
      'txt': 'gray.500',
      'csv': 'teal.500',
      'tsv': 'teal.500',
    };
    
    return colorMap[ext] || 'gray.500';
  };

  return (
    <Container maxW="container.xl" py={4}>
      <Grid templateColumns="repeat(12, 1fr)" gap={4}>
        {/* Repository selector */}
        <GridItem colSpan={12} mb={4}>
          <HStack spacing={4} justify="space-between">
            <HStack>
              <Icon as={IoGitBranch} fontSize="xl" color="gray.600" />
              <Heading size="md">Repository Browser</Heading>
            </HStack>
            
            {/* GitHub Connector Dropdown */}
            <Box>
              <Select
                placeholder="Select GitHub Repository"
                value={selectedConnector?.id || ''}
                onChange={(e) => handleConnectorChange(e.target.value)}
                width="300px"
                isDisabled={loading}
              >
                {githubConnectors.map(connector => (
                  <option key={connector.id} value={connector.id}>
                    {connector.name} ({connector.repo_url})
                  </option>
                ))}
              </Select>
            </Box>
          </HStack>
          <Divider my={2} />
        </GridItem>
        
        {/* File explorer sidebar */}
        <GridItem colSpan={{ base: 12, md: 3 }} borderRight="1px" borderColor="gray.200" height="calc(100vh - 180px)" overflowY="auto">
          <VStack align="stretch" spacing={3}>
            <InputGroup size="sm">
              <InputLeftElement pointerEvents="none">
                <Icon as={IoSearch} color="gray.400" />
              </InputLeftElement>
              <Input 
                placeholder="Search files..." 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </InputGroup>
            
            {loading && !fileTree.length ? (
              <Box textAlign="center" py={8}>
                <Spinner />
              </Box>
            ) : (
              <>
                {renderFileTree(fileTree)}
                {fileTree.length === 0 && !loading && (
                  <Box textAlign="center" py={8}>
                    <Text color="gray.500">No files found</Text>
                  </Box>
                )}
              </>
            )}
          </VStack>
        </GridItem>
        
        {/* Main content area */}
        <GridItem colSpan={{ base: 12, md: 9 }} height="calc(100vh - 180px)" overflowY="auto">
          {selectedFile ? (
            <Box>
              <Flex justifyContent="space-between" alignItems="center" mb={2}>
                <HStack spacing={2}>
                  <Icon as={IoDocument} color="gray.600" />
                  <Text fontWeight="bold">{selectedFile.name}</Text>
                </HStack>
                
                {/* Show lineage button with larger, more prominent design */}
                {lineageData && (
                  <HStack spacing={2}>
                    <Button
                      leftIcon={<Icon as={IoGitNetwork} />}
                      colorScheme={showLineage ? "orange" : "blue"}
                      size="md"
                      onClick={() => setShowLineage(!showLineage)}
                      variant={showLineage ? "solid" : "outline"}
                    >
                      {showLineage ? "Hide Lineage" : "Show Lineage"}
                    </Button>
                    <Tooltip label="Data lineage shows column-level relationships between tables">
                      <IconButton
                        icon={<Icon as={IoAnalytics} />}
                        size="sm"
                        colorScheme="gray"
                        variant="ghost"
                        aria-label="Lineage info"
                      />
                    </Tooltip>
                  </HStack>
                )}
              </Flex>
              
              <Divider mb={4} />
              
              {loading ? (
                <Box textAlign="center" py={8}>
                  <Spinner />
                </Box>
              ) : (
                <>
                  {showLineage && lineageData ? (
                    <Box 
                      height="calc(100vh - 250px)" 
                      border="1px" 
                      borderColor="blue.200" 
                      borderRadius="md" 
                      p={3}
                      boxShadow="md"
                      bg="white"
                    >
                      <Flex justify="space-between" align="center" mb={3}>
                        <Heading size="sm" color="blue.700">
                          Data Lineage Visualization
                        </Heading>
                        <HStack>
                          <Button
                            leftIcon={<Icon as={IoCode} />}
                            size="xs"
                            colorScheme="blue"
                            onClick={() => {
                              console.log('Current lineage data:', lineageData);
                            }}
                          >
                            Debug Data
                          </Button>
                          <Button
                            leftIcon={<Icon as={IoDocument} />}
                            size="xs"
                            colorScheme="gray"
                            onClick={() => setShowLineage(false)}
                          >
                            Back to Code
                          </Button>
                        </HStack>
                      </Flex>
                      <Box height="calc(100% - 40px)" borderRadius="md" overflow="hidden" position="relative">
                        {lineageData && Object.keys(lineageData).length > 0 ? (
                          <LineageGraph data={lineageData} width="100%" height="100%" />
                        ) : (
                          <Box 
                            position="absolute" 
                            top="50%" 
                            left="50%" 
                            transform="translate(-50%, -50%)"
                            textAlign="center"
                            p={4}
                            borderRadius="md"
                            bg="red.50"
                            border="1px"
                            borderColor="red.200"
                          >
                            <Icon as={IoWarning} color="red.500" boxSize={8} mb={2} />
                            <Text fontWeight="bold" color="red.600" mb={2}>Lineage Visualization Error</Text>
                            <Text color="red.600">Could not render the lineage graph with the available data.</Text>
                          </Box>
                        )}
                      </Box>
                    </Box>
                  ) : (
                    <Box
                      position="relative"
                      borderRadius="md"
                      border="1px"
                      borderColor="gray.200"
                      overflow="auto"
                      bg="gray.50"
                      fontSize="sm"
                    >
                      {/* Prominent lineage icon overlay for SQL files when not viewing lineage */}
                      {lineageData && (
                        <Box
                          position="absolute"
                          top="10px"
                          right="10px"
                          zIndex="1"
                        >
                          <IconButton
                            icon={<Icon as={IoGitNetwork} />}
                            colorScheme="blue"
                            size="sm"
                            onClick={() => setShowLineage(true)}
                            aria-label="Show lineage"
                          />
                        </Box>
                      )}
                      
                      <SyntaxHighlighter
                        language={getFileExtension(selectedFile?.name || '')}
                        style={docco}
                        showLineNumbers
                        customStyle={{ 
                          backgroundColor: 'transparent',
                          fontSize: '0.9em',
                          fontFamily: 'monospace',
                          padding: '20px'
                        }}
                      >
                        {fileContent}
                      </SyntaxHighlighter>
                    </Box>
                  )}
                </>
              )}
            </Box>
          ) : (
            <Box
              height="100%"
              display="flex"
              flexDirection="column"
              justifyContent="center"
              alignItems="center"
              color="gray.500"
            >
              <Icon as={IoDocument} fontSize="6xl" mb={4} />
              <Text>Select a file to view its contents</Text>
            </Box>
          )}
        </GridItem>
      </Grid>
    </Container>
  );
};

export default RepositoryPage;
