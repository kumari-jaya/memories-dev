import spacy
import re
import logging
import os
from typing import Dict, Any, Optional, Tuple

class LocationExtractor:
    """A class to extract location information from text using spaCy."""
    
    def __init__(self):
        """Initialize the Location Extraction system with spaCy."""
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            # If model is not found, download it
            os.system("python -m spacy download en_core_web_sm")
            self.nlp = spacy.load("en_core_web_sm")
        
        self.logger = logging.getLogger(__name__)
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    def extract_coordinates(self, text: str) -> Optional[Tuple[float, float]]:
        """
        Extract coordinates from text using regex patterns.
        
        Args:
            text (str): Input text containing potential coordinates
            
        Returns:
            Optional[Tuple[float, float]]: Tuple of (latitude, longitude) if found, None otherwise
        """
        patterns = [
            r'\(?\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*\)?',  # (12.345, 67.890) or 12.345, 67.890
            r'(-?\d+\.?\d*)\s*°\s*[NSns]\s*,\s*(-?\d+\.?\d*)\s*°\s*[EWew]',  # 12.345°N, 67.890°E
            r'(-?\d+\.?\d*)\s*[NSns]\s*,\s*(-?\d+\.?\d*)\s*[EWew]'  # 12.345N, 67.890E
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    lat = float(match.group(1))
                    lon = float(match.group(2))
                    
                    # Handle South and West coordinates
                    if 'S' in text.upper() or 's' in text:
                        lat = -lat
                    if 'W' in text.upper() or 'w' in text:
                        lon = -lon
                    
                    # Validate coordinate ranges
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        return (lat, lon)
                except ValueError:
                    continue
        return None

    def process_query(self, user_query: str) -> Dict[str, Any]:
        """
        Process the query to extract location and information type.
        
        Args:
            user_query (str): User's input query
            
        Returns:
            Dict[str, Any]: Dictionary containing location and location type
        """
        try:
            # First check for coordinates
            coordinates = self.extract_coordinates(user_query)
            if coordinates:
                return {
                    "location": f"{coordinates[0]}, {coordinates[1]}",
                    "location_type": "point",
                    "coordinates": coordinates
                }
            
            # Process with spaCy for named entities
            doc = self.nlp(user_query)
            
            # Look for location entities
            locations = []
            for ent in doc.ents:
                if ent.label_ in ["GPE", "LOC", "FAC"]:
                    locations.append((ent.text, ent.label_))
            
            # If no entities found, check for state names specifically
            if not locations:
                # Common state indicators
                state_indicators = ["state", "province"]
                words = user_query.split()
                for i, word in enumerate(words):
                    if word.lower() in state_indicators:
                        if i > 0:
                            state_name = words[i-1]  # Get the word before "state"
                            locations.append((state_name, "GPE"))  # Only store the state name
                        elif i < len(words) - 1:
                            state_name = words[i+1]  # Get the word after "state"
                            locations.append((state_name, "GPE"))  # Only store the state name
            
            if locations:
                # Get the first location found
                location_text, label = locations[0]
                
                # Determine location type based on entity label and text characteristics
                location_type = "unknown"
                if label == "GPE":
                    words = user_query.lower().split()
                    if "state" in words or "province" in words:
                        location_type = "state"
                    elif len(location_text.split()) == 1:
                        location_type = "city"
                    else:
                        location_type = "address"
                elif label == "LOC":
                    location_type = "point"
                elif label == "FAC":
                    location_type = "address"
                
                return {
                    "location": location_text,
                    "location_type": location_type,
                    "coordinates": None
                }
            
            return {
                "location": "",
                "location_type": "",
                "coordinates": None
            }
            
        except Exception as e:
            self.logger.error(f"Error processing query: {str(e)}")
            return {
                "location": "",
                "location_type": "",
                "coordinates": None
            }

from memories_dev.utils.query.location_extractor import LocationExtractor

def test_location_extractor():
    # Initialize the extractor
    extractor = LocationExtractor()
    
    # Test cases
    test_queries = [
        "Find airports near 51.150750, -108.799436"
    ]
    
    # Process each test query
    for query in test_queries:
        print("\nQuery:", query)
        result = extractor.process_query(query)
        print("Result:", result)

if __name__ == "__main__":
    test_location_extractor()
