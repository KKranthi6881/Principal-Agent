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
  Select,
  Collapse,
  Badge
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
  IoCheckmark,
  IoSettings,
  IoCodeSlash,
  IoColorPalette,
  IoGrid,
  IoTerminal,
  IoWarning,
  IoLogoPython,
  IoLogoJavascript
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

  // Process URL parameters to open specific file when provided
  useEffect(() => {
    // Parse URL query parameters
    const queryParams = new URLSearchParams(location.search);
    const repoParam = queryParams.get('repo');
    const pathParam = queryParams.get('path');
    const fileParam = queryParams.get('file');
    
    console.log('URL Parameters:', { repoParam, pathParam, fileParam });
    console.log('Available GitHub connectors:', githubConnectors);
    
    // Only proceed if we have all the necessary parameters
    if (repoParam && fileParam) {
      // Find or select the correct repository
      const loadRepository = async () => {
        // Wait for connectors to be loaded
        if (githubConnectors.length === 0) {
          console.log('No GitHub connectors available yet, waiting...');
          return;
        }
        
        // Print full details of all connectors for debugging
        console.log('GitHub Connectors for matching:');
        githubConnectors.forEach((c, index) => {
          console.log(`Connector ${index}:`, {
            id: c.id,
            name: c.name,
            repo_url: c.repo_url,
          });
        });
        
        // Special case for the dbt-labs repository that's causing issues
        if (repoParam.includes('dbt-labs') || repoParam.includes('dbt-cloud-snowflake-demo-template')) {
          console.log('Detected dbt-labs repository, using special handling');
          // Find any connector that might be suitable
          const dbtConnector = githubConnectors.find(c => 
            c.repo_url && (
              c.repo_url.includes('dbt-labs') || 
              c.repo_url.includes('dbt-cloud') || 
              c.repo_url.includes('snowflake')
            )
          );
          
          // If no matching connectors, use the first available one
          let connector = dbtConnector || githubConnectors[0];
          
          if (connector) {
            console.log('Using connector for dbt-labs repository:', connector);
            setSelectedConnector(connector);
            await fetchFileTree(connector.repo_url);
            
            // After file tree is loaded, find and open the specific file
            // Try multiple times with increasing delays to ensure file tree is populated
            let attempts = 0;
            const maxAttempts = 5;
            const tryOpenFile = () => {
              attempts++;
              if (fileTree && fileTree.length > 0) {
                console.log(`Attempt ${attempts}: File tree loaded, trying to open file:`, fileParam);
                const success = openFileFromPath(fileParam);
                if (!success && attempts < maxAttempts) {
                  // If file not found and we haven't exceeded max attempts, try again
                  console.log(`File not found on attempt ${attempts}, trying again...`);
                  setTimeout(tryOpenFile, 500 * attempts); // Increasing delay with each attempt
                }
              } else if (attempts < maxAttempts) {
                // File tree not loaded yet, try again
                console.log(`Attempt ${attempts}: File tree not loaded yet, retrying...`);
                setTimeout(tryOpenFile, 500 * attempts);
              } else {
                console.error('Failed to open file after maximum attempts:', fileParam);
                toast({
                  title: 'File Not Found',
                  description: `Could not open file: ${fileParam}. The file may not exist in the repository.`,
                  status: 'warning',
                  duration: 5000,
                  isClosable: true,
                });
              }
            };
            
            // Start trying to open the file
            setTimeout(tryOpenFile, 500);
            return;
          }
        }
        
        // Find the matching repository connector
        let connector = githubConnectors.find(c => {
          // Check if repo URL contains the repo parameter
          if (c.repo_url) {
            // Extract owner/repo from URL
            try {
              const normalizedConnectorUrl = normalizeGitHubUrl(c.repo_url);
              console.log('Normalized connector URL:', normalizedConnectorUrl);
              
              // Multiple matching strategies for greater flexibility
              
              // Strategy 1: Direct path comparison (owner/repo)
              const urlObj = new URL(normalizedConnectorUrl);
              const pathParts = urlObj.pathname.split('/').filter(Boolean);
              const repoString = pathParts.length >= 2 ? `${pathParts[0]}/${pathParts[1]}` : '';
              
              // Strategy 2: Compare just the repo name (for cases where formats differ)
              const repoName = pathParts.length >= 2 ? pathParts[1].replace('.git', '') : '';
              
              // Log comparison values for debugging
              console.log('Comparing:', { 
                repoParam, 
                repoString,
                repoName,
                connectorUrl: c.repo_url 
              });
              
              // More flexible matching - match either the full path or just the repo name
              // This handles cases where format differs between connector and URL parameter
              return (
                repoString === repoParam || 
                repoParam.includes(repoName) || 
                normalizedConnectorUrl.includes(repoParam)
              );
            } catch (e) {
              console.error('Error comparing repo URLs:', e);
              return false;
            }
          }
          return false;
        });
        
        // If no connector was found by URL matching, try a more lenient approach
        if (!connector) {
          console.log('No connector found with exact URL match, trying fallback approach');
          
          // Try matching by repo name pattern in either direction
          connector = githubConnectors.find(c => {
            if (c.repo_url) {
              try {
                // Extract repo name without owner
                const urlObj = new URL(normalizeGitHubUrl(c.repo_url));
                const pathParts = urlObj.pathname.split('/').filter(Boolean);
                const repoName = pathParts.length >= 2 ? pathParts[1].replace('.git', '') : '';
                
                // Split the repository parameter to get the repo name part
                const repoParamParts = repoParam.split('/');
                const repoParamName = repoParamParts.length >= 2 ? repoParamParts[1] : repoParam;
                
                // Check if either contains the other
                return (
                  repoName.includes(repoParamName) || 
                  repoParamName.includes(repoName) ||
                  c.repo_url.includes(repoParam) ||
                  repoParam.includes(repoName)
                );
              } catch (e) {
                return false;
              }
            }
            return false;
          });
        }
        
        // If found, select it and load its file tree
        if (connector) {
          console.log('Found matching connector for repo:', repoParam, connector);
          setSelectedConnector(connector);
          await fetchFileTree(connector.repo_url);
          
          // After file tree is loaded, find and open the specific file
          // Try multiple times with increasing delays to ensure file tree is populated
          let attempts = 0;
          const maxAttempts = 5;
          const tryOpenFile = () => {
            attempts++;
            if (fileTree && fileTree.length > 0) {
              console.log(`Attempt ${attempts}: File tree loaded, trying to open file:`, fileParam);
              const success = openFileFromPath(fileParam);
              if (!success && attempts < maxAttempts) {
                // If file not found and we haven't exceeded max attempts, try again
                console.log(`File not found on attempt ${attempts}, trying again...`);
                setTimeout(tryOpenFile, 500 * attempts); // Increasing delay with each attempt
              }
            } else if (attempts < maxAttempts) {
              // File tree not loaded yet, try again
              console.log(`Attempt ${attempts}: File tree not loaded yet, retrying...`);
              setTimeout(tryOpenFile, 500 * attempts);
            } else {
              console.error('Failed to open file after maximum attempts:', fileParam);
              toast({
                title: 'File Not Found',
                description: `Could not open file: ${fileParam}. The file may not exist in the repository.`,
                status: 'warning',
                duration: 5000,
                isClosable: true,
              });
            }
          };
          
          // Start trying to open the file
          setTimeout(tryOpenFile, 500);
        } else {
          console.warn('No matching repository connector found for:', repoParam);
          toast({
            title: 'Repository not found',
            description: `Could not find a connector for repository: ${repoParam}`,
            status: 'warning',
            duration: 5000,
            isClosable: true,
          });
        }
      };
      
      loadRepository();
    }
  }, [location, githubConnectors]);

  // Helper function to find and open a file by its path
  const openFileFromPath = (filePath) => {
    if (!filePath) {
      console.warn('No file path provided to openFileFromPath');
      return false;
    }
    
    // Ensure path doesn't have leading slash
    const normalizedPath = filePath.startsWith('/') ? filePath.substring(1) : filePath;
    console.log('Opening file from path:', normalizedPath);
    
    // Try to find the file in the file tree
    const findAndOpenFile = (nodes, targetPath) => {
      for (const node of nodes) {
        // Try multiple path matching strategies
        const nodeMatchesPath = 
          // Exact path match
          node.path === targetPath || 
          // Case insensitive match
          node.path.toLowerCase() === targetPath.toLowerCase() ||
          // Path ending match (for cases where repository prefixes are different)
          (node.path.endsWith(targetPath) && node.type === 'file');
        
        // Check if this is the file we're looking for
        if (nodeMatchesPath && node.type === 'file') {
          console.log('Found matching file:', node);
          
          // Expand parent folders
          expandParentFolders(node.path);
          
          // Select the file and fetch its content
          setSelectedFile({
            path: node.path,
            name: node.name || node.path.split('/').pop(),
            repo: selectedConnector?.repo_url || '',
            type: 'file'
          });
          
          // Update the URL to reflect current file selection
          updateBrowserUrl(node.path);
          
          // Fetch file content
          fetchFileContent(selectedConnector?.repo_url, node.path);
          return true;
        }
        
        // Check children if this is a directory
        if (node.children && node.children.length > 0) {
          if (findAndOpenFile(node.children, targetPath)) {
            return true;
          }
        }
      }
      
      return false;
    };
    
    // Try to find and open the file
    if (fileTree && fileTree.length > 0) {
      if (findAndOpenFile(fileTree, normalizedPath)) {
        return true;
      } else {
        console.warn('Could not find the specified file in the file tree:', normalizedPath);
        return false;
      }
    } else {
      console.warn('File tree is empty, cannot open file:', normalizedPath);
      return false;
    }
  };

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

  // Helper function to normalize GitHub URLs to owner/repo format as per our standards
  const normalizeGitHubUrl = (url) => {
    if (!url) return '';
    
    try {
      // Handle URLs with http/https
      if (url.startsWith('http')) {
        const parsedUrl = new URL(url);
        let pathParts = parsedUrl.pathname.split('/');
        // Remove empty parts
        pathParts = pathParts.filter(part => part.length > 0);
        
        if (pathParts.length >= 2) {
          // Standard GitHub URL format
          const owner = pathParts[0];
          // Remove .git suffix if present
          const repo = pathParts[1].replace(/\.git$/, '');
          return `${owner}/${repo}`;
        }
      } else if (url.includes('/')) {
        // Already in owner/repo format, just clean it up
        const parts = url.split('/');
        if (parts.length >= 2) {
          const owner = parts[0].trim();
          // Remove .git suffix if present
          const repo = parts[1].trim().replace(/\.git$/, '');
          return `${owner}/${repo}`;
        }
      }
      
      // If we can't parse it, return as is
      return url;
    } catch (error) {
      console.error('Error normalizing GitHub URL:', error);
      return url;
    }
  };

  // Fetch only the top-level files and folders initially (lazy loading approach)
  const fetchFileTree = async (repoUrl) => {
    try {
      setLoading(true);
      setFileTree([]);
      setSelectedFile(null);
      setFileContent('');
      setExpandedFolders({root: true, '': true}); // Reset expanded folders
      
      if (!repoUrl) {
        console.error('No repository URL provided');
        setLoading(false);
        return;
      }
      
      console.log('Fetching top-level files for repository:', repoUrl);
      
      // Extract repo owner/name from URL for API call
      const repoParam = normalizeGitHubUrl(repoUrl);
      console.log('Normalized repo param for API call:', repoParam);
      
      // Step 1: Fetch only root level files
      const rootResponse = await fetch(`/api/github/local/files?repo=${encodeURIComponent(repoParam)}`);
      
      if (!rootResponse.ok) {
        console.error(`Root fetch failed: ${rootResponse.status}`);
        setLoading(false);
        return;
      }
      
      const rootData = await rootResponse.json();
      if (!rootData?.files || !Array.isArray(rootData.files)) {
        console.error('Invalid root data structure:', rootData);
        setLoading(false);
        return;
      }
      
      console.log(`Root fetch successful: ${rootData.files.length} items`, rootData.files);
      
      // Process the files to ensure they have the right structure
      const processedFiles = rootData.files.map(file => ({
        ...file,
        path: file.path || file.name,
        isDirectory: file.type === 'dir',
        children: file.type === 'dir' ? [] : null,
        loaded: false // Track if folder contents have been loaded
      }));
      
      // Set initial file tree with just the top level
      setFileTree(processedFiles);
      setLoading(false);
      
      return true;
    } catch (error) {
      console.error('Error fetching file tree:', error);
      toast({
        title: 'Error',
        description: `Failed to fetch repository files: ${error.message}`,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
      setLoading(false);
      return false;
    }
  };

  // Expand all top-level folders and fetch their contents
  const expandAllTopLevelFolders = () => {
    console.log('Auto-expanding top-level folders');
    
    // Find all directories in the file tree
    const foldersToExpand = fileTree.filter(node => node.type === 'dir' || node.isDirectory);
    console.log(`Found ${foldersToExpand.length} top-level folders to expand`);
    
    if (foldersToExpand.length > 0) {
      // Update expanded folders state
      const newExpandedState = { ...expandedFolders };
      foldersToExpand.forEach(folder => {
        newExpandedState[folder.path] = true;
        console.log(`Marking folder as expanded: ${folder.path}`);
      });
      setExpandedFolders(newExpandedState);
      
      // Fetch contents for each folder
      foldersToExpand.forEach(folder => {
        console.log(`Auto-fetching contents for: ${folder.path}`);
        fetchFolderContents(selectedConnector?.repo_url, folder.path);
      });
    }
    
    setInitialExpanded(true);
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
    console.log("Valid files count:", validFiles.length);
    
    // Log sample file for debugging
    if (validFiles.length > 0) {
      console.log("Sample file entry:", validFiles[0]);
    }
    
    // First pass: Create node objects for each file/directory
    validFiles.forEach(file => {
      const isDir = file.is_dir || file.type === 'dir' || file.path.endsWith('/');
      const filePath = file.path.replace(/\/$/, ''); // Remove trailing slash
      const pathParts = filePath.split('/');
      const fileName = pathParts[pathParts.length - 1] || filePath;
      
      // Skip if already processed
      if (paths[filePath]) return;
      
      // Create node for this file/directory
      paths[filePath] = {
        name: fileName,
        path: filePath,
        type: isDir ? 'dir' : 'file',
        isDirectory: isDir,
        children: isDir ? [] : null,
        parent: pathParts.length > 1 ? pathParts.slice(0, -1).join('/') : ''
      };
      
      // Generate parent directories if they don't exist
      if (pathParts.length > 1) {
        // Create parent directories
        for (let i = 1; i < pathParts.length; i++) {
          const parentPath = pathParts.slice(0, i).join('/');
          if (!paths[parentPath]) {
            paths[parentPath] = {
              name: pathParts[i-1],
              path: parentPath,
              type: 'dir',
              isDirectory: true,
              children: [],
              parent: i > 1 ? pathParts.slice(0, i-1).join('/') : ''
            };
          }
        }
      }
    });

    // Second pass: Build parent-child relationships
    Object.values(paths).forEach(node => {
      // Add top-level items to tree
      if (!node.parent) {
        tree.push(node);
      } else if (paths[node.parent]) {
        // Add as child to parent
        const parent = paths[node.parent];
        if (!parent.children) parent.children = [];
        
        // Avoid duplicates
        if (!parent.children.some(child => child.path === node.path)) {
          parent.children.push(node);
        }
      } else {
        // If parent doesn't exist, add to root
        console.log(`Parent not found for ${node.path}, adding to root`);
        tree.push(node);
      }
    });

    // Sort function for tree nodes
    const sortNodes = (nodes) => {
      if (!nodes) return;
      
      // Sort: directories first, then alphabetically by name
      nodes.sort((a, b) => {
        if ((a.type === 'dir') !== (b.type === 'dir')) {
          return a.type === 'dir' ? -1 : 1;
        }
        return a.name.localeCompare(b.name);
      });
      
      // Sort children recursively
      nodes.forEach(node => {
        if (node.children && node.children.length > 0) {
          sortNodes(node.children);
        }
      });
    };
    
    // Sort the entire tree
    sortNodes(tree);
    
    console.log(`Built file tree with ${tree.length} root items`);
    return tree;
  };

  // This helper function has been replaced by the improved version above
  // that follows the standardized URL handling approach

  // Fetch file content from the GitHub API or local repository
  const fetchFileContent = async (repo, path) => {
    if (!repo || !path) {
      console.error('Missing required parameters for fetchFileContent', { repo, path });
      return;
    }
    
    try {
      setLoading(true);
      console.log(`Fetching content for ${path} in repo ${repo}`);
      
      // Update the UI to show which file is selected
      setSelectedFile({ path, name: path.split('/').pop() });
      
      // Normalize repo URL to owner/repo format using our standardized approach
      const repoParam = normalizeGitHubUrl(repo);
      console.log(`Using normalized repo parameter: ${repoParam}`);
      
      let response;
      let data;
      
      // First try local repository API with the standardized format
      try {
        console.log(`Trying local API for file content: repo=${repoParam}, path=${path}`);
        response = await fetch(`/api/github/local/content?repo=${encodeURIComponent(repoParam)}&path=${encodeURIComponent(path)}`);
        
        if (response.ok) {
          data = await response.json();
          console.log('Local file content response:', data);
        } else {
          console.log(`Local API file content failed with status: ${response.status}`);
        }
      } catch (localError) {
        console.log('Local content fetch failed, will try GitHub API:', localError);
      }
      
      // Fall back to GitHub API if local fetch failed
      if (!data) {
        console.log('Trying GitHub API for file content');
        // Use the same normalized repo parameter for consistency
        response = await fetch(`/api/github/content?repo=${encodeURIComponent(repoParam)}&path=${encodeURIComponent(path)}`);
        
        if (!response.ok) {
          throw new Error(`API error: ${response.status} ${response.statusText}`);
        }
        
        data = await response.json();
        console.log('GitHub API file content response received');
      }
      
      if (data && data.content) {
        // Update file content
        setFileContent(data.content);
        
        // Update browser URL with the file path
        updateBrowserUrl(path);
        
        // Attempt to fetch lineage data (for SQL files and YAML/YML files)
        if (path.toLowerCase().endsWith('.sql') || path.toLowerCase().endsWith('.yml') || path.toLowerCase().endsWith('.yaml')) {
          fetchLineageData(repoParam, path);
        } else {
          // Reset lineage data for non-SQL/non-YAML files
          setLineageData(null);
          setShowLineage(false);
        }
      } else {
        setFileContent('Empty file or no content available');
      }
    } catch (error) {
      console.error('Error fetching file content:', error);
      toast({
        title: 'Error',
        description: `Failed to fetch file content: ${error.message}`,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      setFileContent(`Error loading file: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Helper function to build standardized GitHub paths
  const _buildGithubPath = (repo, path) => {
    try {
      // First normalize the repo URL
      const normalizedRepo = normalizeGitHubUrl(repo);
      
      // Extract owner/repo format that's consistent across all agents
      let ownerRepo;
      
      if (normalizedRepo.startsWith('http')) {
        // Handle URL format (like https://github.com/owner/repo)
        const repoUrl = new URL(normalizedRepo);
        ownerRepo = repoUrl.pathname.substring(1); // Remove leading slash
      } else {
        // Already in owner/repo format
        ownerRepo = normalizedRepo;
      }
      
      // Remove any .git suffix
      ownerRepo = ownerRepo.replace(/\.git$/, '');
      
      // Ensure path doesn't start with / to avoid double slashes
      const cleanPath = path.startsWith('/') ? path.substring(1) : path;
      
      // Return the standardized GitHub path
      return `${ownerRepo}/${cleanPath}`;
    } catch (error) {
      console.error('Error building GitHub path:', error);
      // Fallback for safety
      return `${repo.replace(/\/$/, '')}/${path}`;
    }
  };

  // Fetch lineage data for the selected file using standardized URL handling
  const fetchLineageData = async (repo, path) => {
    if (!repo || !path) return;
    try {
      // Build a standardized GitHub path following our URL handling standards
      let githubPath = _buildGithubPath(repo, path);
      console.log('Fetching lineage for standardized path:', githubPath);
      
      // Call the lineage API endpoint with the standardized path
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
            source: rel.source.table_id, 
            target: rel.target.table_id, 
            type: rel.type || 'depends_on'
          }));
      } else if (models.length > 0) {
        // Create at least one edge if we have models but no relationships
        // This ensures we have something to display
        if (models.length === 1) {
          // Self-reference for single model
          edges = [{
            id: 'self-edge',
            source: models[0].id, 
            target: models[0].id, 
            type: 'self'
          }];
        } else if (models.length > 1) {
          // Connect first two models
          edges = [{
            id: 'default-edge',
            source: models[0].id, 
            target: models[1].id, 
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
  
  // Helper function to update the browser URL when navigating the file tree
  const updateBrowserURL = (repoUrl, path) => {
    try {
      if (!repoUrl) return;
      
      // Extract owner/repo from the URL
      const repoParam = normalizeGitHubUrl(repoUrl);
      const pathParts = repoParam.split('/');
      
      if (pathParts.length >= 2) {
        // Create new URL with the current folder path
        const newUrl = new URL(window.location.origin + '/repository');
        newUrl.searchParams.set('repo', repoParam);
        
        if (path) {
          newUrl.searchParams.set('path', path);
        }
        
        // Update browser URL without reloading the page
        window.history.pushState({}, '', newUrl.toString());
        console.log('Updated browser URL to folder:', newUrl.toString());
      }
    } catch (e) {
      console.error('Failed to update browser URL:', e);
    }
  };

  // Toggle folder expanded/collapsed state with lazy loading
  const toggleFolder = async (folderPath) => {
    console.log(`Toggling folder: ${folderPath}`);
    
    // Check if we're expanding or collapsing
    const isCurrentlyExpanded = expandedFolders[folderPath] === true;
    const willExpand = !isCurrentlyExpanded;
    
    // If we're expanding the folder and it has a connector selected
    if (willExpand && selectedConnector) {
      // Find the folder node in our file tree
      const folderNode = findNodeByPath(fileTree, folderPath);
      
      // Only fetch contents if this is a directory and we haven't loaded it yet
      if (folderNode && (folderNode.isDirectory || folderNode.type === 'dir') && 
          (!folderNode.loaded || folderNode.children.length === 0)) {
        console.log(`Lazy loading contents for folder: ${folderPath}`);
        
        try {
          // Set temporary loading state
          setFileTree(prevTree => {
            const updatedTree = JSON.parse(JSON.stringify(prevTree));
            const updateNodeLoading = (nodes) => {
              for (let i = 0; i < nodes.length; i++) {
                if (nodes[i].path === folderPath) {
                  nodes[i].loading = true;
                  return true;
                }
                if (nodes[i].children && nodes[i].children.length > 0) {
                  if (updateNodeLoading(nodes[i].children)) return true;
                }
              }
              return false;
            };
            updateNodeLoading(updatedTree);
            return updatedTree;
          });
          
          // Call API to fetch folder contents
          const repoParam = normalizeGitHubUrl(selectedConnector.repo_url);
          const response = await fetch(
            `/api/github/local/files?repo=${encodeURIComponent(repoParam)}&path=${encodeURIComponent(folderPath)}`
          );
          
          if (response.ok) {
            const data = await response.json();
            
            if (data?.files && Array.isArray(data.files)) {
              // Process the folder contents
              const processedChildren = data.files.map(file => ({
                ...file,
                path: file.path || `${folderPath}/${file.name}`,
                isDirectory: file.type === 'dir',
                children: file.type === 'dir' ? [] : null,
                loaded: false // Children aren't loaded until expanded
              }));
              
              // Update file tree with folder contents
              setFileTree(prevTree => {
                const updatedTree = JSON.parse(JSON.stringify(prevTree));
                const updateNode = (nodes) => {
                  for (let i = 0; i < nodes.length; i++) {
                    if (nodes[i].path === folderPath) {
                      nodes[i].children = processedChildren;
                      nodes[i].loading = false;
                      nodes[i].loaded = true;
                      return true;
                    }
                    if (nodes[i].children && nodes[i].children.length > 0) {
                      if (updateNode(nodes[i].children)) return true;
                    }
                  }
                  return false;
                };
                updateNode(updatedTree);
                return updatedTree;
              });
            }
          } else {
            console.error(`Failed to load folder contents: ${response.status}`);
          }
        } catch (error) {
          console.error(`Error loading contents for ${folderPath}:`, error);
          // Clear loading state on error
          setFileTree(prevTree => {
            const updatedTree = JSON.parse(JSON.stringify(prevTree));
            const updateNode = (nodes) => {
              for (let i = 0; i < nodes.length; i++) {
                if (nodes[i].path === folderPath) {
                  nodes[i].loading = false;
                  return true;
                }
                if (nodes[i].children && nodes[i].children.length > 0) {
                  if (updateNode(nodes[i].children)) return true;
                }
              }
              return false;
            };
            updateNode(updatedTree);
            return updatedTree;
          });
        }
      }
    }
    
    // Toggle expanded state (regardless of whether we fetched contents)
    setExpandedFolders(prev => {
      const newState = { ...prev };
      newState[folderPath] = willExpand;
      
      // Update URL to reflect the current path
      if (selectedConnector) {
        updateBrowserUrl(folderPath);
      }
      
      return newState;
    });
  };
  
  // Check if a folder is expanded
  const isFolderExpanded = (folderPath) => {
    return expandedFolders[folderPath] === true;
  };

  // Fetch the contents of a folder to expand
  const fetchFolderContents = async (repoUrl, folderPath) => {
    if (!repoUrl || folderPath === undefined) return;
    
    try {
      console.log(`Fetching folder contents for ${folderPath} in ${repoUrl}`);
      
      // Extract owner and repo
      let owner, repo;
      try {
        const normalizedRepo = normalizeGitHubUrl(repoUrl);
        const urlObj = new URL(normalizedRepo);
        const pathParts = urlObj.pathname.split('/').filter(Boolean);
        if (pathParts.length >= 2) {
          owner = pathParts[0];
          repo = pathParts[1].replace('.git', '');
        }
      } catch (e) {
        console.error('Failed to parse repo URL:', e);
        return;
      }
      
      // Use local API if possible
      if (owner && repo) {
        const repoParam = `${owner}/${repo}`;
        const encodedPath = encodeURIComponent(folderPath);
        const url = `/api/github/local/files?repo=${encodeURIComponent(repoParam)}&path=${encodedPath}`;
        
        console.log(`Fetching from: ${url}`);
        
        try {
          const response = await fetch(url);
          if (response.ok) {
            const data = await response.json();
            console.log(`Received folder contents for ${folderPath}:`, data);
            
            if (data && data.files && Array.isArray(data.files)) {
              // Process the received files
              const processedFiles = data.files.map(file => ({
                ...file,
                // Ensure path is properly set
                path: file.path || (folderPath ? `${folderPath}/${file.name}` : file.name),
                // Add isDirectory property for consistent handling
                isDirectory: file.type === 'dir',
                // Initialize empty children array for directories
                children: file.type === 'dir' ? [] : null
              }));
              
              // Update the file tree with the new files
              updateFileTreeWithFolderContents(folderPath, processedFiles);
              return true;
            } else {
              console.log(`No files found in ${folderPath} or invalid response`);
            }
          } else {
            console.error(`Failed to fetch folder contents: ${response.status}`);
            const errorText = await response.text();
            console.error(`Error details: ${errorText}`);
          }
        } catch (error) {
          console.error('Error fetching folder contents from local API:', error);
          toast({
            title: 'Error',
            description: `Failed to fetch folder contents: ${error.message}`,
            status: 'error',
            duration: 3000,
            isClosable: true,
          });
        }
      }
    } catch (error) {
      console.error('Error in fetchFolderContents:', error);
    }
    
    return false;
  };

  // Update the file tree with fetched folder contents
  const updateFileTreeWithFolderContents = (folderPath, files) => {
    // Don't update if no files found
    if (!files || files.length === 0) {
      console.log(`No files to update for ${folderPath}`);
      return;
    }
    
    console.log(`Updating tree with ${files.length} items for ${folderPath}`);
    
    setFileTree(prevTree => {
      // Create a deep copy of the tree to avoid direct state mutation
      const newTree = JSON.parse(JSON.stringify(prevTree));
      
      // If it's the root folder
      if (!folderPath || folderPath === '') {
        return files;
      }
      
      // Find the folder node to update
      const updateNodeChildren = (nodes, path) => {
        for (let i = 0; i < nodes.length; i++) {
          const node = nodes[i];
          
          // Check if this is the node we're looking for
          if (node.path === path || node.path === path + '/') {
            console.log(`Found node to update: ${node.path}`);
            // Replace the children array with the new files
            node.children = files;
            return true;
          }
          
          // Check children recursively if this is a directory
          if (node.children && node.children.length > 0) {
            const found = updateNodeChildren(node.children, path);
            if (found) return true;
          }
        }
        
        return false;
      };
      
      const updated = updateNodeChildren(newTree, folderPath);
      if (!updated) {
        console.warn(`Could not find folder ${folderPath} in the file tree to update`);
      }
      
      return newTree;
    });
  };

  // Helper function for search in children nodes
  const searchInChildren = (nodes, query) => {
    if (!nodes) return false;
    return nodes.some(node => {
      const nameMatch = node.name.toLowerCase().includes(query);
      const childrenMatch = node.children && searchInChildren(node.children, query);
      return nameMatch || childrenMatch;
    });
  };
  
  // Render file tree recursively with improved GitHub-style appearance
  const renderFileTree = (nodes, depth = 0) => {
    if (!nodes) {
      return <Text color="gray.500" pl={depth > 0 ? 6 : 0} py={2}>No files found</Text>;
    }
    if (nodes.length === 0) {
      return <Text color="gray.500" pl={depth > 0 ? 6 : 0} py={2}>No files found</Text>;
    }
    
    // Filter nodes if search is active
    let filteredNodes = nodes;
    if (searchQuery) {
      const lowerQuery = searchQuery.toLowerCase();
      filteredNodes = nodes.filter(node => {
        const nameMatch = node.name.toLowerCase().includes(lowerQuery);
        const childrenMatch = node.children && searchInChildren(node.children, lowerQuery);
        return nameMatch || childrenMatch;
      });
    }
    
    // Sort nodes: directories first, then alphabetically (GitHub style)
    filteredNodes.sort((a, b) => {
      const aIsDir = a.type === 'dir' || a.isDirectory;
      const bIsDir = b.type === 'dir' || b.isDirectory;
      if (aIsDir && !bIsDir) return -1;
      if (!aIsDir && bIsDir) return 1;
      return a.name.localeCompare(b.name);
    });
    
    return filteredNodes.map((node, index) => {
      if (!node) return null;
      
      const isExpanded = isFolderExpanded(node.path);
      const isDirectory = node.type === 'dir' || node.isDirectory === true;
      const isSelected = selectedFile && selectedFile.path === node.path;
      const nodeName = node.name || node.path.split('/').pop() || node.path;
      
      // GitHub-style indentation (16px per level)
      const indentSize = depth * 4;
      
      if (isDirectory) {
        // Folder rendering - GitHub style
        return (
          <Box 
            key={node.path + '-' + index} 
            mb={0.5}
          >
            <HStack
              py={1.5}
              px={2}
              pl={indentSize + 2}
              spacing={2}
              cursor="pointer"
              bg={isSelected ? 'blue.50' : 'transparent'}
              _hover={{ bg: isSelected ? 'blue.50' : 'gray.50' }}
              onClick={() => toggleFolder(node.path)}
              alignItems="center"
              role="group"
              width="100%"
            >
              {/* GitHub-style folder icon */}
              <Icon 
                as={isExpanded ? IoFolderOpen : IoFolder} 
                color={isExpanded ? "blue.500" : "gray.500"}
                boxSize={4}
                mr={1}
              />
              
              {/* Folder name - GitHub style */}
              <Text 
                fontWeight={isExpanded ? "medium" : "normal"}
                fontSize="sm"
                color={isExpanded ? "blue.600" : "gray.900"}
                isTruncated={false} // Important: Don't truncate folder names
                flex="1"
              >
                {nodeName}
              </Text>
              
              {/* Subtle item count */}
              {node.children && node.children.length > 0 && (
                <Text 
                  color="gray.500" 
                  fontSize="xs"
                  mr={1}
                  opacity={0.8}
                >
                  {node.children.length}
                </Text>
              )}
              
              {/* Expansion indicator - GitHub style chevron */}
              <Icon 
                as={isExpanded ? IoChevronDown : IoChevronForward} 
                color="gray.500"
                boxSize={3.5}
                opacity={0.7}
                transition="transform 0.2s"
              />
            </HStack>
            
            {/* Children container - GitHub style nested files */}
            <Collapse in={isExpanded} animateOpacity={false}>
              <Box>
                {node.children && node.children.length > 0 ? (
                  renderFileTree(node.children, depth + 1)
                ) : (
                  <Box pl={indentSize + 8} py={1.5}>
                    <Text fontSize="xs" color="gray.500">
                      Empty folder
                    </Text>
                  </Box>
                )}
              </Box>
            </Collapse>
          </Box>
        );
      } else {
        // File item rendering - GitHub style
        return (
          <HStack
            key={node.path + '-' + index}
            py={1.5}
            px={2}
            pl={indentSize + 2}
            spacing={2}
            cursor="pointer"
            bg={isSelected ? 'blue.50' : 'transparent'}
            _hover={{ bg: 'gray.50' }}
            alignItems="center"
            role="group"
            width="100%"
            onClick={() => {
              setSelectedFile({
                ...node,
                path: node.path,
                name: nodeName,
                type: 'file',
                isDirectory: false
              });
              fetchFileContent(selectedConnector?.repo_url, node.path);
              expandParentFolders(node.path);
            }}
          >
            {/* File icon - GitHub style */}
            <Icon 
              as={getFileIcon(nodeName)} 
              color={getFileIconColor(nodeName)} 
              boxSize={4}
              mr={1}
            />
            
            {/* File name - GitHub style with NO truncation */}
            <Text 
              fontSize="sm" 
              color="gray.800"
              fontWeight={isSelected ? "medium" : "normal"}
              isTruncated={false} // Important: Don't truncate file names
              flex="1"
            >
              {nodeName}
            </Text>
            
            {/* Lineage icon for data files - more subtle but visible */}
            {!isDirectory && ['sql', 'yml', 'yaml'].includes(getFileExtension(nodeName)) && (
              <Tooltip label="View data lineage" placement="top" hasArrow>
                <IconButton
                  icon={<Icon as={IoGitNetwork} boxSize={3.5} />}
                  size="xs"
                  variant="ghost"
                  colorScheme="blue"
                  opacity={isSelected ? 0.9 : 0.4}
                  _groupHover={{ opacity: 0.9 }}
                  aria-label="View lineage"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (selectedConnector) {
                      fetchFileContent(selectedConnector.repo_url, node.path);
                      setSelectedFile({
                        ...node,
                        path: node.path,
                        name: nodeName,
                        type: 'file'
                      });
                      fetchLineageData(selectedConnector.repo_url, node.path).then(() => {
                        setShowLineage(true);
                      });
                    }
                  }}
                />
              </Tooltip>
            )}
          </HStack>
        );
      }
    });
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
    
    // Special case for configuration files
    if (fileName.startsWith('.') || fileName === 'Dockerfile' || fileName === 'Makefile') {
      return IoSettings;
    }
    
    // Map file extensions to appropriate icons
    const iconMap = {
      // Code files
      'sql': IoAnalytics,  // Changed to Analytics for data files
      'py': IoLogoPython, // More specific Python icon
      'js': IoLogoJavascript, // More specific JS icon
      'jsx': IoLogoJavascript,
      'ts': IoLogoJavascript,  // TypeScript
      'tsx': IoLogoJavascript,
      
      // Data/config files
      'yml': IoList,
      'yaml': IoList,
      'json': IoCodeSlash,
      'csv': IoGrid,  // Better icon for tabular data
      'tsv': IoGrid,
      
      // Content files
      'md': IoDocument,
      'txt': IoDocument,
      'html': IoCode,
      'css': IoColorPalette, // Better icon for styling
      
      // Git related
      'gitignore': IoGitBranch,
      'gitattributes': IoGitBranch,
      
      // Executable
      'sh': IoTerminal,
      'bash': IoTerminal,
    };
    
    return iconMap[ext] || IoDocument;
  };
  
  // Get color based on file type
  const getFileIconColor = (fileName) => {
    if (!fileName) return 'gray.500';
    
    const ext = fileName.split('.').pop().toLowerCase();
    
    // Special case for configuration files
    if (fileName.startsWith('.') || fileName === 'Dockerfile' || fileName === 'Makefile') {
      return 'gray.600';
    }
    
    // Map file extensions to appropriate colors
    const colorMap = {
      // Code files with vibrant colors
      // Code files with distinctive colors
      'sql': 'purple.500',      // Data files in purple
      'yml': 'teal.500',        // Config files in teal
      'yaml': 'teal.500',
      'md': 'gray.600',         // Documentation in subdued gray
      'json': 'orange.500',     // JSON in orange
      'py': 'blue.500',         // Python in blue
      'js': 'yellow.500',       // JavaScript in yellow
      'jsx': 'yellow.600',      // JSX slightly darker
      'ts': 'blue.600',         // TypeScript in blue
      'tsx': 'blue.700',        // TSX slightly darker
      
      // Markup and styling
      'html': 'red.500',
      'css': 'pink.500',
      'scss': 'pink.600',
      'sass': 'pink.600',
      
      // Data formats
      'txt': 'gray.500',
      'csv': 'green.500',
      'tsv': 'green.500',
      'xml': 'orange.600',
      
      // Scripts
      'sh': 'gray.700',
      'bash': 'gray.700',
    };

    return colorMap[ext] || 'gray.500';
  };

  // Helper function to update browser URL without refreshing the page
  const updateBrowserUrl = (filePath) => {
    if (!selectedConnector || !selectedConnector.repo_url) return;
    
    // Extract owner/repo from the connector URL
    try {
      const normalizedUrl = normalizeGitHubUrl(selectedConnector.repo_url);
      const urlObj = new URL(normalizedUrl);
      const pathParts = urlObj.pathname.split('/').filter(Boolean);
      if (pathParts.length >= 2) {
        const repoParam = `${pathParts[0]}/${pathParts[1]}`;
        
        // Create new URL with the current file path
        const newUrl = new URL(window.location.origin + '/repository');
        newUrl.searchParams.set('repo', repoParam);
        
        if (filePath) {
          // Extract folder path and file name
          const lastSlashIndex = filePath.lastIndexOf('/');
          
          if (lastSlashIndex >= 0) {
            // Set path to the directory containing the file
            const dirPath = filePath.substring(0, lastSlashIndex + 1);
            newUrl.searchParams.set('path', dirPath);
            // Set file to the full path for exact file reference
            newUrl.searchParams.set('file', filePath);
          } else {
            // For files in the root directory
            newUrl.searchParams.set('path', '/');
            newUrl.searchParams.set('file', filePath);
          }
        }
        
        // Update browser URL without reloading the page
        window.history.pushState({}, '', newUrl.toString());
        console.log('Updated browser URL:', newUrl.toString());
      }
    } catch (e) {
      console.error('Failed to update browser URL:', e);
    }
  };


return (
  <Container maxW="container.xl" py={4}>
    <Grid templateColumns="repeat(12, 1fr)" gap={4}>
      {/* Repository selector header */}
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
      <GridItem 
        colSpan={{ base: 12, md: 3 }} 
        borderRight="1px" 
        borderColor="gray.200" 
        overflowY="auto" 
        height="calc(100vh - 180px)"
        position="relative"
        bg="white"
        boxShadow="sm"
      >
        {/* File search bar */}
        <Box 
          position="sticky" 
          top="0" 
          zIndex="2" 
          bg="white" 
          pt={3} 
          pb={2} 
          px={2}
          borderBottom="1px" 
          borderColor="gray.100"
        >
          <InputGroup size="sm">
            <InputLeftElement pointerEvents="none">
              <Icon as={IoSearch} color="gray.400" />
            </InputLeftElement>
            <Input 
              placeholder="Search files..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              bg="gray.50"
              _hover={{ bg: "white" }}
              _focus={{ bg: "white", borderColor: "blue.300" }}
              borderRadius="md"
            />
          </InputGroup>
        </Box>

        {/* File tree container */}
        <Box p={2} overflowY="auto" h="calc(100% - 60px)">
          {loading && !fileTree.length ? (
            <Box textAlign="center" py={8}>
              <Spinner color="blue.500" size="md" />
              <Text mt={2} color="gray.500" fontSize="sm">Loading repository...</Text>
            </Box>
          ) : (
            <VStack align="stretch" spacing={1}>
              {renderFileTree(fileTree)}
              {fileTree.length === 0 && !loading && (
                <Box textAlign="center" py={8} borderRadius="md" bg="gray.50">
                  <Icon as={IoDocument} color="gray.400" boxSize={8} mb={2} />
                  <Text color="gray.500">No files found</Text>
                </Box>
              )}
            </VStack>
          )}
        </Box>
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
