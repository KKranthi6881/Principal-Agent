import React, { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import {
  Box,
  Heading,
  Button,
  useColorModeValue,
  Text,
  VStack,
  HStack,
  Badge,
  Icon
} from '@chakra-ui/react';
import { IoExpand, IoContract, IoDownload, IoInformation } from 'react-icons/io5';

export const LineageVisualizer = ({ data }) => {
  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const [expanded, setExpanded] = React.useState(false);
  
  // Check if we have valid data to render
  if (!data || !data.models || !data.edges || data.models.length === 0) {
    return (
      <Box 
        mt={3} 
        p={3} 
        borderRadius="md" 
        bg="yellow.50" 
        borderWidth="1px" 
        borderColor="yellow.200"
      >
        <HStack>
          <Icon as={IoInformation} color="yellow.500" />
          <Text fontSize="sm">No lineage data available for visualization</Text>
        </HStack>
      </Box>
    );
  }
  
  useEffect(() => {
    if (!data || !svgRef.current || !containerRef.current) return;
    
    // Clear previous graph
    d3.select(svgRef.current).selectAll("*").remove();
    
    // Set up dimensions
    const containerWidth = containerRef.current.offsetWidth;
    const margin = { top: 40, right: 40, bottom: 40, left: 40 };
    const width = containerWidth - margin.left - margin.right;
    const height = (expanded ? 500 : 300) - margin.top - margin.bottom;
    
    // Create SVG
    const svg = d3.select(svgRef.current)
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom)
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);
    
    // Create simulation
    const simulation = d3.forceSimulation()
      .force("link", d3.forceLink().id(d => d.id).distance(150))
      .force("charge", d3.forceManyBody().strength(-500))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(70));
    
    // Process nodes and links
    const nodes = data.models.map(model => ({
      id: model.id || model.name,
      name: model.name,
      type: model.type || 'table',
      schema: model.schema || 'unknown'
    }));
    
    const links = data.edges.map(edge => ({
      source: edge.source,
      target: edge.target,
      type: edge.type || 'depends_on'
    }));
    
    // Define color schemes
    const nodeColors = {
      table: useColorModeValue("#805AD5", "#D6BCFA"),      // purple
      view: useColorModeValue("#3182CE", "#90CDF4"),       // blue
      source: useColorModeValue("#38A169", "#9AE6B4"),     // green
      transformation: useColorModeValue("#DD6B20", "#FBD38D"), // orange
      model: useColorModeValue("#805AD5", "#D6BCFA"),      // purple
      default: useColorModeValue("#718096", "#A0AEC0")     // gray
    };
    
    // Create links
    const link = svg.append("g")
      .attr("stroke", "#999")
      .attr("stroke-opacity", 0.6)
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke-width", 1.5)
      .attr("marker-end", "url(#arrowhead)");
    
    // Define arrow marker
    svg.append("defs").append("marker")
      .attr("id", "arrowhead")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 25)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("fill", "#999")
      .attr("d", "M0,-5L10,0L0,5");
    
    // Create node groups
    const node = svg.append("g")
      .selectAll(".node")
      .data(nodes)
      .join("g")
      .attr("class", "node")
      .call(d3.drag()
        .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended));
    
    // Add rectangles for nodes
    node.append("rect")
      .attr("width", d => Math.max(d.name.length * 8 + 20, 100))
      .attr("height", 40)
      .attr("rx", 5)
      .attr("ry", 5)
      .attr("fill", d => nodeColors[d.type] || nodeColors.default)
      .attr("stroke", "#555")
      .attr("stroke-width", 1);
    
    // Add text to nodes
    node.append("text")
      .attr("dx", 10)
      .attr("dy", 25)
      .attr("fill", "white")
      .style("font-size", "12px")
      .style("font-weight", "bold")
      .text(d => d.name);
    
    // Add labels for schema/type
    node.append("text")
      .attr("dx", 10)
      .attr("dy", -5)
      .attr("fill", "#333")
      .style("font-size", "10px")
      .text(d => d.schema)
      .style("opacity", expanded ? 1 : 0);
    
    // Update positions in simulation
    simulation.nodes(nodes).on("tick", ticked);
    simulation.force("link").links(links);
    
    // Functions for drag behavior
    function dragstarted(event, d) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    }
    
    function dragged(event, d) {
      d.fx = event.x;
      d.fy = event.y;
    }
    
    function dragended(event, d) {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    }
    
    // Update positions on tick
    function ticked() {
      link
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);
      
      node
        .attr("transform", d => `translate(${d.x - 50},${d.y - 20})`);
    }
    
  }, [data, expanded]);
  
  // Download SVG as PNG
  const downloadAsPNG = () => {
    const svg = svgRef.current;
    if (!svg) return;
    
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    const svgWidth = svg.width.baseVal.value;
    const svgHeight = svg.height.baseVal.value;
    
    canvas.width = svgWidth;
    canvas.height = svgHeight;
    
    // Draw white background
    context.fillStyle = 'white';
    context.fillRect(0, 0, svgWidth, svgHeight);
    
    // Convert SVG to data URL
    const svgData = new XMLSerializer().serializeToString(svg);
    const img = new Image();
    
    img.onload = () => {
      context.drawImage(img, 0, 0);
      const a = document.createElement('a');
      a.download = 'lineage-diagram.png';
      a.href = canvas.toDataURL('image/png');
      a.click();
    };
    
    img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)));
  };
  
  return (
    <Box 
      ref={containerRef} 
      mt={4} 
      p={4} 
      borderWidth="1px" 
      borderColor="gray.200"
      borderRadius="md"
      bg="white"
      boxShadow="sm"
    >
      <VStack align="stretch" spacing={4}>
        <HStack justify="space-between" align="center">
          <Heading size="sm" color="gray.700">Data Lineage</Heading>
          <HStack>
            <Button 
              size="xs" 
              leftIcon={expanded ? <IoContract /> : <IoExpand />} 
              onClick={() => setExpanded(!expanded)}
              colorScheme="purple"
              variant="outline"
            >
              {expanded ? 'Collapse' : 'Expand'}
            </Button>
            <Button 
              size="xs" 
              leftIcon={<IoDownload />} 
              onClick={downloadAsPNG}
              colorScheme="blue"
              variant="outline"
            >
              Download
            </Button>
          </HStack>
        </HStack>
        
        <Box 
          overflowX="auto" 
          borderWidth="1px" 
          borderColor="gray.100" 
          borderRadius="md"
          bg="gray.50"
        >
          <svg ref={svgRef}></svg>
        </Box>
        
        <HStack spacing={3} wrap="wrap">
          {Object.entries(data.models.reduce((acc, model) => {
            if (!acc[model.type]) acc[model.type] = 0;
            acc[model.type]++;
            return acc;
          }, {})).map(([type, count]) => (
            <Badge 
              key={type} 
              px={2} 
              py={1} 
              borderRadius="md" 
              colorScheme={
                type === 'table' ? 'purple' : 
                type === 'view' ? 'blue' : 
                type === 'source' ? 'green' : 
                type === 'transformation' ? 'orange' : 'gray'
              }
            >
              {type}: {count}
            </Badge>
          ))}
        </HStack>
      </VStack>
    </Box>
  );
}; 