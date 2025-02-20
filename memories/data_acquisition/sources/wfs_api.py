"""
Web Feature Service (WFS) data source for vector data.
"""

import os
from typing import Dict, List, Optional, Tuple, Union
from pathlib import Path
import logging
from shapely.geometry import box, Polygon
import geopandas as gpd
from owslib.wfs import WebFeatureService
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WFSAPI:
    """Interface for accessing data from WFS services."""
    
    def __init__(
        self,
        cache_dir: Optional[str] = None,
        timeout: int = 30,
        usgs_url: Optional[str] = None,
        geoserver_url: Optional[str] = None,
        mapserver_url: Optional[str] = None,
        wfs_version: str = "2.0.0"
    ):
        """
        Initialize WFS client.
        
        Args:
            cache_dir: Directory for caching data
            timeout: Timeout for WFS requests in seconds
            usgs_url: URL for USGS WFS service
            geoserver_url: URL for GeoServer WFS service
            mapserver_url: URL for MapServer WFS service
            wfs_version: WFS version to use (default: 2.0.0)
        """
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".wfs_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        
        # Define available WFS endpoints based on provided URLs
        self.endpoints = {}
        
        if usgs_url:
            self.endpoints["usgs"] = {
                "url": usgs_url,
                "version": wfs_version
            }
        
        if geoserver_url:
            self.endpoints["geoserver"] = {
                "url": geoserver_url,
                "version": wfs_version
            }
        
        if mapserver_url:
            self.endpoints["mapserver"] = {
                "url": mapserver_url,
                "version": wfs_version
            }
        
        if not self.endpoints:
            logger.warning("No WFS endpoints provided. Please provide at least one WFS service URL.")
        
        # Initialize WFS clients
        self.services = self._init_services()
    
    def _init_services(self) -> Dict:
        """Initialize WFS service connections."""
        services = {}
        for name, config in self.endpoints.items():
            try:
                service = WebFeatureService(
                    url=config["url"],
                    version=config["version"],
                    timeout=self.timeout
                )
                services[name] = service
                logger.info(f"Successfully initialized WFS service: {name}")
            except Exception as e:
                logger.error(f"Failed to initialize WFS service {name}: {e}")
        return services
    
    def get_features(
        self,
        bbox: Union[Tuple[float, float, float, float], Polygon],
        layers: List[str],
        service_name: str,
        max_features: int = 1000,
        output_format: str = "GeoJSON"
    ) -> Dict[str, gpd.GeoDataFrame]:
        """
        Get vector features from a WFS service.
        
        Args:
            bbox: Bounding box or Polygon
            layers: List of layers to fetch
            service_name: Name of the service to use (usgs, geoserver, or mapserver)
            max_features: Maximum number of features to return
            output_format: Output format (GeoJSON, GML, etc.)
            
        Returns:
            Dictionary mapping layer names to GeoDataFrames containing the features
        """
        # Validate bbox format
        if isinstance(bbox, (list, tuple)):
            if len(bbox) != 4:
                raise ValueError("Bounding box must be a tuple/list of 4 coordinates (minx, miny, maxx, maxy)")
            bbox = list(float(x) for x in bbox)  # Convert to list of floats
        elif isinstance(bbox, Polygon):
            bbox = list(bbox.bounds)  # Convert to list
        else:
            raise ValueError("Bounding box must be a tuple/list of coordinates or a Polygon")
        
        if service_name not in self.services:
            logger.error(f"Service {service_name} not found or not initialized")
            return {}
            
        service = self.services[service_name]
        results = {}
        
        try:
            # Get available layers
            available_layers = list(service.contents)
            logger.info(f"Available layers in {service_name}: {available_layers}")
            
            # Filter requested layers
            layers_to_fetch = [
                layer for layer in layers
                if layer in available_layers
            ]
            
            if not layers_to_fetch:
                logger.warning(f"No requested layers available in {service_name}")
                return {}
            
            for layer in layers_to_fetch:
                try:
                    # Get layer info
                    layer_info = service.contents[layer]
                    
                    # Check if bbox is within layer bounds
                    if not self._is_bbox_valid(bbox, layer_info.boundingBoxWGS84):
                        logger.warning(
                            f"Bbox {bbox} outside layer bounds for {layer}"
                        )
                        continue
                    
                    # Request features
                    response = service.getfeature(
                        typename=layer,
                        bbox=bbox,
                        maxfeatures=max_features,
                        outputFormat=output_format
                    )
                    
                    # Parse response
                    if output_format == "GeoJSON":
                        features = json.loads(response.read())
                        gdf = gpd.GeoDataFrame.from_features(features)
                    else:
                        # Handle other formats if needed
                        logger.warning(
                            f"Output format {output_format} not fully supported"
                        )
                        continue
                    
                    if not gdf.empty:
                        results[layer] = gdf
                        
                except Exception as e:
                    logger.error(f"Error fetching layer {layer} from {service_name}: {e}")
            
        except Exception as e:
            logger.error(f"Error accessing WFS service {service_name}: {e}")
        
        return results
    
    def _is_bbox_valid(
        self,
        request_bbox: Tuple[float, float, float, float],
        layer_bbox: Tuple[float, float, float, float]
    ) -> bool:
        """Check if requested bbox is within layer bounds."""
        # Extract coordinates
        req_minx, req_miny, req_maxx, req_maxy = request_bbox
        lay_minx, lay_miny, lay_maxx, lay_maxy = layer_bbox
        
        # Check if request bbox is completely outside layer bbox
        if (req_maxx < lay_minx or req_minx > lay_maxx or
            req_maxy < lay_miny or req_miny > lay_maxy):
            return False
        
        return True
    
    def get_layer_info(
        self,
        layer: str,
        service_name: str
    ) -> Optional[Dict]:
        """Get detailed information about a layer."""
        if service_name not in self.services:
            logger.error(f"Service {service_name} not found or not initialized")
            return None
            
        service = self.services[service_name]
        try:
            if layer in service.contents:
                layer_info = service.contents[layer]
                return {
                    "title": layer_info.title,
                    "abstract": layer_info.abstract,
                    "keywords": layer_info.keywords,
                    "bbox": layer_info.boundingBoxWGS84,
                    "crs": layer_info.crsOptions,
                    "properties": [
                        getattr(op, 'name', op).replace("MagicMock name='", "").replace("'", "").split(".")[0]
                        for op in layer_info.properties
                    ] if hasattr(layer_info, "properties") else []
                }
        except Exception as e:
            logger.error(f"Error getting layer info from {service_name}: {e}")
        
        return None
    
    def get_available_layers(
        self,
        service_name: str
    ) -> List[str]:
        """Get available layers from a WFS service."""
        if service_name not in self.services:
            logger.error(f"Service {service_name} not found or not initialized")
            return []
            
        service = self.services[service_name]
        try:
            return list(service.contents.keys())
        except Exception as e:
            logger.error(f"Error getting layers from {service_name}: {e}")
            return []
    
    def download_to_file(
        self,
        bbox: Union[Tuple[float, float, float, float], Polygon],
        layers: List[str],
        output_dir: str,
        service_name: str,
        format: str = "GeoJSON"
    ) -> Dict[str, Path]:
        """
        Download vector data to files.
        
        Args:
            bbox: Bounding box or Polygon
            layers: List of layers to fetch
            output_dir: Directory to save files
            service_name: Name of the service to use
            format: Output format
            
        Returns:
            Dictionary mapping layer names to file paths
        """
        results = self.get_features(
            bbox=bbox,
            layers=layers,
            service_name=service_name,
            output_format=format
        )
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        file_paths = {}
        for layer_name, gdf in results.items():
            if not gdf.empty:
                file_path = output_dir / f"{layer_name}.geojson"
                gdf.to_file(file_path, driver="GeoJSON")
                file_paths[layer_name] = file_path
        
        return file_paths 