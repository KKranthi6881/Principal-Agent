import axios from 'axios';

// API base URL from environment or default to localhost
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8080';

// Create axios instance with base configuration
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// GitHub connector API functions
const githubConnectorApi = {
  // Get all GitHub connectors
  getAllConnectors: async () => {
    try {
      const response = await api.get('/api/settings/github_connectors');
      return response.data;
    } catch (error) {
      console.error('Error fetching GitHub connectors:', error);
      throw error;
    }
  },

  // Get a specific GitHub connector by ID
  getConnector: async (connectorId) => {
    try {
      const response = await api.get(`/api/settings/github_connectors/${connectorId}`);
      return response.data;
    } catch (error) {
      console.error(`Error fetching GitHub connector ${connectorId}:`, error);
      throw error;
    }
  },

  // Create a new GitHub connector
  createConnector: async (connectorData) => {
    try {
      // Convert snake_case to camelCase if needed
      const formattedData = {
        username: connectorData.username,
        token: connectorData.token,
        repo_url: connectorData.repoUrl || connectorData.repo_url,
        is_public: connectorData.isPublic || connectorData.is_public,
        is_enterprise: connectorData.isEnterprise || connectorData.is_enterprise,
        tech_stack: connectorData.techStack || connectorData.tech_stack || 'postgresql',
      };
      
      const response = await api.post('/api/settings/github_connectors', formattedData);
      return response.data;
    } catch (error) {
      console.error('Error creating GitHub connector:', error);
      throw error;
    }
  },

  // Update an existing GitHub connector
  updateConnector: async (connectorId, connectorData) => {
    try {
      // Convert snake_case to camelCase if needed
      const formattedData = {
        username: connectorData.username,
        token: connectorData.token,
        repo_url: connectorData.repoUrl || connectorData.repo_url,
        is_public: connectorData.isPublic || connectorData.is_public,
        is_enterprise: connectorData.isEnterprise || connectorData.is_enterprise,
        tech_stack: connectorData.techStack || connectorData.tech_stack,
      };
      
      // Remove undefined values
      Object.keys(formattedData).forEach(key => 
        formattedData[key] === undefined && delete formattedData[key]
      );
      
      const response = await api.put(`/api/settings/github_connectors/${connectorId}`, formattedData);
      return response.data;
    } catch (error) {
      console.error(`Error updating GitHub connector ${connectorId}:`, error);
      throw error;
    }
  },

  // Delete a GitHub connector
  deleteConnector: async (connectorId) => {
    try {
      const response = await api.delete(`/api/settings/github_connectors/${connectorId}`);
      return response.status === 204; // Return true if deletion was successful
    } catch (error) {
      console.error(`Error deleting GitHub connector ${connectorId}:`, error);
      throw error;
    }
  }
};

export default githubConnectorApi; 