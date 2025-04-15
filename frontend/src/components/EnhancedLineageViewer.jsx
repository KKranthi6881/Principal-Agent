import React, { useRef, useEffect, useState } from 'react';
import {
  Box,
  Text,
  HStack,
  VStack,
  Badge,
  IconButton,
  Tooltip,
  useColorModeValue,
  Flex,
  Button,
} from '@chakra-ui/react';
import { FiZoomIn, FiZoomOut, FiMaximize2, FiMinimize2 } from 'react-icons/fi';
import { RiRestartLine } from 'react-icons/ri';
import { IoExpand, IoContract, IoDownload } from 'react-icons/io5';
import { TbArrowsHorizontal, TbArrowsVertical, TbMapPin } from 'react-icons/tb';
import cytoscape from 'cytoscape';
import dagre from 'cytoscape-dagre';
import popper from 'cytoscape-popper';
import tippy from 'tippy.js';
import 'tippy.js/dist/tippy.css';

// Register extensions properly
if (typeof cytoscape('core', 'dagre') === 'undefined') {
  cytoscape.use(dagre);
}

if (typeof cytoscape('collection', 'popper') === 'undefined') {
  cytoscape.use(popper);
}

// ErrorBoundary component
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("Error in lineage viewer:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Box p={4} borderRadius="md" bg="red.50" color="red.700">
          <Text fontWeight="bold">Error rendering lineage view</Text>
          <Text fontSize="sm">{this.state.error?.message || 'Unknown error'}</Text>
        </Box>
      );
    }

    return this.props.children;
  }
}

const EnhancedLineageViewer = ({ data, isMaximized, onMaximizeToggle }) => {
  const cyRef = useRef(null);
  const containerRef = useRef(null);
  const [cy, setCy] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [modelCounts, setModelCounts] = useState({
    tables: 0,
    queries: 0,
    total: 0
  });
  const [layoutMode, setLayoutMode] = useState('horizontal');
  const [isPanningMode, setIsPanningMode] = useState(false);

  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.600');

  // Node type to color mapping (similar to LineageGraph)
  const nodeTypeColors = {
    'source': '#38A169',    // green.500
    'staging': '#3182CE',   // blue.500
    'intermediate': '#8B5CF6', // purple.500
    'mart': '#10B981',      // green.500
    'table': '#0EA5E9',     // sky.500
    'upstream': '#06B6D4',  // cyan.500
    'view': '#3182CE',      // blue.500
    'default': '#64748B'    // slate.500
  };

  const handleZoomIn = () => {
    if (cy) {
      cy.zoom(cy.zoom() * 1.2);
      setZoomLevel(cy.zoom());
    }
  };

  const handleZoomOut = () => {
    if (cy) {
      cy.zoom(cy.zoom() / 1.2);
      setZoomLevel(cy.zoom());
    }
  };

  const handleReset = () => {
    if (cy) {
      cy.fit();
      cy.center();
      setZoomLevel(cy.zoom());
    }
  };

  const toggleLayoutMode = () => {
    const newMode = layoutMode === 'horizontal' ? 'vertical' : 'horizontal';
    setLayoutMode(newMode);
    
    // Update the layout with new orientation
    if (cy) {
      const layout = cy.layout({
        name: 'dagre',
        rankDir: newMode === 'horizontal' ? 'LR' : 'TB',
        padding: 50,
        spacingFactor: 1.5,
        animate: true,
        animationDuration: 500
      });
      
      layout.run();
      
      // Fit and center after layout completes
      setTimeout(() => {
        cy.fit();
        cy.center();
      }, 600);
    }
  };

  const togglePanningMode = () => {
    setIsPanningMode(!isPanningMode);
    
    if (cy) {
      // Toggle dragging behavior based on panning mode
      if (!isPanningMode) {
        // Enable panning mode
        cy.userPanningEnabled(true);
        cy.boxSelectionEnabled(false);
        cy.nodes().ungrabify();
      } else {
        // Disable panning mode
        cy.userPanningEnabled(true);
        cy.boxSelectionEnabled(true);
        cy.nodes().grabify();
      }
    }
  };

  const downloadAsImage = () => {
    if (!cy) return;
    
    const png64 = cy.png({
      full: true,
      scale: 2,
      bg: 'white',
      output: 'blob'
    });
    
    // Convert to URL and download
    const url = URL.createObjectURL(png64);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'lineage-diagram.png';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  useEffect(() => {
    if (containerRef.current && data) {
      // Clean up previous instance
      if (cyRef.current) {
        cyRef.current.destroy();
      }

      // Transform data into cytoscape format
      const transformData = () => {
        const nodes = [];
        const edges = [];
        
        // Process nodes first
        if (data.models && Array.isArray(data.models)) {
          data.models.forEach(model => {
            if (!model.id) {
              console.warn('Model missing ID:', model);
              return;
            }
            
            // Get color based on model type
            const nodeType = model.type || 'default';
            const color = nodeTypeColors[nodeType] || nodeTypeColors.default;
            
            nodes.push({
              data: {
                id: model.id,
                label: model.name || 'Unnamed',
                nodeType: nodeType,
                description: model.path || '',
                highlight: model.highlight || false,
                color: color
              }
            });
          });
        }
        
        // Process edges, ensuring they reference valid nodes
        if (data.edges && Array.isArray(data.edges)) {
          const nodeIds = new Set(nodes.map(node => node.data.id));
          
          data.edges.forEach(edge => {
            // Skip edges with missing source or target
            if (!edge.source || !edge.target) {
              console.warn('Edge missing source or target:', edge);
              return;
            }
            
            // Skip edges referencing non-existent nodes
            if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
              console.warn('Edge references non-existent node:', 
                `source: ${edge.source}, target: ${edge.target}`);
              return;
            }
            
            // Create a unique ID for the edge
            const edgeId = `edge-${edge.source}-${edge.target}`;
            
            edges.push({
              data: {
                id: edgeId,
                source: edge.source,
                target: edge.target,
                label: edge.label || ''
              }
            });
          });
        }
        
        return { nodes, edges };
      };
      
      // Transform the data
      const { nodes, edges } = transformData();
      
      // Count models by type
      const typeCounts = {};
      nodes.forEach(node => {
        const type = node.data.nodeType;
        typeCounts[type] = (typeCounts[type] || 0) + 1;
      });
      
      // Set model counts with more detailed breakdown
      setModelCounts({
        tables: typeCounts['table'] || 0,
        staging: typeCounts['staging'] || 0,
        intermediate: typeCounts['intermediate'] || 0,
        mart: typeCounts['mart'] || 0,
        source: typeCounts['source'] || 0,
        total: nodes.length
      });

      // Create new cytoscape instance
      const config = {
        container: containerRef.current,
        elements: {
          nodes: nodes,
          edges: edges
        },
        style: [
          {
            selector: 'node',
            style: {
              'background-color': 'data(color)',
              'label': 'data(label)',
              'color': '#FFF',
              'text-valign': 'center',
              'text-halign': 'center',
              'text-wrap': 'wrap',
              'text-max-width': '100px',
              'font-size': '12px',
              'width': '30px',
              'height': '30px',
              'border-width': 1,
              'border-color': '#D6BCFA', // purple.200
              'text-outline-color': '#2D3748', // gray.800
              'text-outline-width': 1,
              'text-outline-opacity': 0.5
            }
          },
          {
            selector: 'node[nodeType = "table"], node[nodeType = "staging"], node[nodeType = "mart"]',
            style: {
              'shape': 'rectangle',
              'width': '120px',
              'height': '40px',
            }
          },
          {
            selector: 'node[nodeType = "source"]',
            style: {
              'shape': 'diamond',
              'width': '40px',
              'height': '40px',
            }
          },
          {
            selector: 'node[nodeType = "intermediate"]',
            style: {
              'shape': 'round-rectangle',
              'width': '120px',
              'height': '40px',
            }
          },
          {
            selector: 'node[highlight = true]',
            style: {
              'border-width': 3,
              'border-color': '#ED8936', // orange.500
              'border-opacity': 1,
              'background-color': 'data(color)',
              'font-weight': 'bold',
              'shadow-color': '#ED8936',
              'shadow-opacity': 0.5,
              'shadow-blur': 10,
              'shadow-offset-x': 0,
              'shadow-offset-y': 0
            }
          },
          {
            selector: 'edge',
            style: {
              'width': 2,
              'line-color': '#CBD5E0', // gray.300
              'target-arrow-color': '#718096', // gray.500
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              'opacity': 0.7,
              'arrow-scale': 1.2
            }
          },
          {
            selector: ':selected',
            style: {
              'background-color': '#E9D8FD', // purple.100
              'border-width': 2,
              'border-color': '#6B46C1', // purple.700
              'line-color': '#6B46C1', // purple.700
              'target-arrow-color': '#6B46C1', // purple.700
              'opacity': 1
            }
          }
        ],
        layout: {
          name: 'dagre',
          rankDir: layoutMode === 'horizontal' ? 'LR' : 'TB',
          padding: 50,
          spacingFactor: 1.5,
          animate: false
        },
        minZoom: 0.2,
        maxZoom: 3,
        wheelSensitivity: 0.3,
      };

      const newCy = cytoscape(config);
      cyRef.current = newCy;
      setCy(newCy);
      setZoomLevel(newCy.zoom());

      // Add tooltips
      try {
        // Simpler approach to tooltips using Cytoscape's built-in events
        newCy.nodes().on('mouseover', function(e) {
          const node = e.target;
          const nodeData = node.data();
          
          // Create tooltip content with LineageGraph-like styling
          const tooltipHtml = `
            <div style="background-color: white; padding: 12px; border-radius: 6px; 
                        box-shadow: 0 4px 12px rgba(0,0,0,0.15); max-width: 250px; 
                        position: absolute; z-index: 1000; font-family: sans-serif;">
              <div style="font-weight: bold; font-size: 14px; margin-bottom: 4px; color: #2D3748;">
                ${nodeData.label || 'Unnamed'}
              </div>
              <div style="display: inline-block; background-color: ${nodeData.color}; 
                          color: white; padding: 2px 8px; border-radius: 4px; 
                          font-size: 12px; margin-bottom: 8px;">
                ${nodeData.nodeType || 'table'}
              </div>
              ${nodeData.description ? 
                `<div style="font-size: 12px; color: #4A5568; margin-top: 4px;">
                  Path: ${nodeData.description}
                </div>` : ''}
            </div>
          `;
          
          // Remove any existing tooltips
          const existingTooltip = document.getElementById('cy-tooltip');
          if (existingTooltip) {
            existingTooltip.remove();
          }
          
          // Create tooltip element
          const tooltipDiv = document.createElement('div');
          tooltipDiv.id = 'cy-tooltip';
          tooltipDiv.innerHTML = tooltipHtml;
          document.body.appendChild(tooltipDiv);
          
          // Position the tooltip near the node
          const renderedPosition = node.renderedPosition();
          const containerRect = containerRef.current.getBoundingClientRect();
          
          tooltipDiv.style.left = (containerRect.left + renderedPosition.x + 10) + 'px';
          tooltipDiv.style.top = (containerRect.top + renderedPosition.y - 40) + 'px';
        });
        
        // Remove tooltip on mouseout
        newCy.nodes().on('mouseout', function() {
          const existingTooltip = document.getElementById('cy-tooltip');
          if (existingTooltip) {
            existingTooltip.remove();
          }
        });
        
        // Also remove tooltip when panning
        newCy.on('pan', function() {
          const existingTooltip = document.getElementById('cy-tooltip');
          if (existingTooltip) {
            existingTooltip.remove();
          }
        });
        
        // Set up node click to center on node
        newCy.on('tap', 'node', function(e) {
          const node = e.target;
          newCy.fit(node, 50);
        });
        
        // Initialize panning mode settings
        if (isPanningMode) {
          newCy.userPanningEnabled(true);
          newCy.boxSelectionEnabled(false);
          newCy.nodes().ungrabify();
        } else {
          newCy.userPanningEnabled(true);
          newCy.boxSelectionEnabled(true);
          newCy.nodes().grabify();
        }
      } catch (err) {
        console.error('Error setting up tooltips:', err);
      }
      
      // Initial fit and center
      setTimeout(() => {
        newCy.fit();
        newCy.center();
        setZoomLevel(newCy.zoom());
      }, 150);

      // Handle resize
      const resizeObserver = new ResizeObserver(() => {
        if (newCy) {
          newCy.resize();
          setTimeout(() => {
            newCy.fit();
            newCy.center();
          }, 150);
        }
      });
      
      resizeObserver.observe(containerRef.current);
      
      return () => {
        if (resizeObserver && containerRef.current) {
          resizeObserver.unobserve(containerRef.current);
        }
        if (cyRef.current) {
          cyRef.current.destroy();
        }
      };
    }
  }, [data, isMaximized, layoutMode, isPanningMode]);

  // Re-center and fit the graph when maximize state changes
  useEffect(() => {
    if (cy) {
      setTimeout(() => {
        cy.resize();
        cy.fit();
        cy.center();
      }, 300); // Longer delay to allow for the drawer animation
    }
  }, [isMaximized, cy]);

  return (
    <Box 
      height="100%" 
      width="100%" 
      position="relative" 
      bg={bgColor}
      display="flex"
      flexDirection="column"
      borderWidth="1px"
      borderColor={borderColor}
      borderRadius="md"
      overflow="hidden"
    >
      {/* Control toolbar - similar to LineageGraph */}
      <Flex 
        justify="space-between" 
        align="center" 
        p={2} 
        borderBottomWidth="1px"
        borderColor={borderColor}
        bg={useColorModeValue('gray.50', 'gray.700')}
      >
        <HStack>
          <Tooltip label="Toggle Layout Direction">
            <IconButton
              icon={layoutMode === 'horizontal' ? <TbArrowsHorizontal /> : <TbArrowsVertical />}
              size="sm"
              onClick={toggleLayoutMode}
              aria-label="Toggle Layout"
              colorScheme="purple"
              variant="ghost"
            />
          </Tooltip>
          <Tooltip label={isPanningMode ? "Exit Pan Mode" : "Pan Mode"}>
            <IconButton
              icon={<TbMapPin />}
              size="sm"
              onClick={togglePanningMode}
              aria-label="Pan Mode"
              colorScheme={isPanningMode ? "blue" : "gray"}
              variant={isPanningMode ? "solid" : "ghost"}
            />
          </Tooltip>
        </HStack>
        
        <HStack>
          <Tooltip label="Zoom In">
            <IconButton 
              icon={<FiZoomIn />} 
              size="sm" 
              onClick={handleZoomIn} 
              aria-label="Zoom In"
              colorScheme="purple"
              variant="ghost"
            />
          </Tooltip>
          <Text fontSize="xs" color="gray.600" fontWeight="medium" minW="40px" textAlign="center">
            {Math.round(zoomLevel * 100)}%
          </Text>
          <Tooltip label="Zoom Out">
            <IconButton 
              icon={<FiZoomOut />} 
              size="sm" 
              onClick={handleZoomOut} 
              aria-label="Zoom Out"
              colorScheme="purple"
              variant="ghost"
            />
          </Tooltip>
          <Tooltip label="Reset View">
            <IconButton 
              icon={<RiRestartLine />} 
              size="sm" 
              onClick={handleReset} 
              aria-label="Reset View"
              colorScheme="purple"
              variant="ghost"
            />
          </Tooltip>
          <Tooltip label="Download PNG">
            <IconButton 
              icon={<IoDownload />} 
              size="sm" 
              onClick={downloadAsImage} 
              aria-label="Download PNG"
              colorScheme="blue"
              variant="ghost"
            />
          </Tooltip>
        </HStack>
      </Flex>
      
      {/* Model type legend - inspired by LineageVisualizer */}
      <Flex
        position="absolute"
        bottom="10px"
        left="10px"
        zIndex={100}
        bg="white"
        p={2}
        borderRadius="md"
        boxShadow="sm"
        direction="column"
        maxW="180px"
      >
        <Text fontSize="xs" fontWeight="bold" mb={1}>Model Types</Text>
        <VStack spacing={1} align="flex-start">
          {Object.entries(modelCounts).filter(([key]) => key !== 'total' && modelCounts[key] > 0).map(([type, count]) => (
            <HStack key={type} spacing={1}>
              <Box 
                w="10px" 
                h="10px" 
                borderRadius={type === 'source' ? 'sm' : 'sm'} 
                bg={nodeTypeColors[type] || nodeTypeColors.default} 
              />
              <Text fontSize="10px" textTransform="capitalize">{type}: </Text>
              <Badge size="sm" fontSize="10px" colorScheme="blue" variant="subtle">{count}</Badge>
            </HStack>
          ))}
        </VStack>
        <Text fontSize="10px" fontWeight="medium" mt={1}>Total: {modelCounts.total} nodes</Text>
      </Flex>
      
      {/* Main graph container */}
      <Box 
        ref={containerRef} 
        height="100%" 
        width="100%"
        overflow="hidden"
        flex="1"
        position="relative"
        cursor={isPanningMode ? "grab" : "default"}
      />
      
      {/* Help tooltip */}
      <Box
        position="absolute"
        bottom="10px"
        right="10px"
        zIndex={100}
        bg="white"
        p={2}
        borderRadius="md"
        boxShadow="sm"
        fontSize="xs"
        color="gray.600"
        maxW="200px"
        opacity={0.8}
        _hover={{ opacity: 1 }}
      >
        <Text fontSize="10px">Tip: Click a node to focus on it</Text>
      </Box>
    </Box>
  );
};

export default EnhancedLineageViewer; 