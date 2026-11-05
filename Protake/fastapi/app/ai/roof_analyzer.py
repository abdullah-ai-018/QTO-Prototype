"""Professional Roofing AI Analysis Engine
Enhanced YOLO detection specifically for comprehensive roof takeoff
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import math

from app.models.enums import RoofType, RoofComplexity, RoofMaterialType, DetectionKind
from app.ai.yolo_detector import detect_objects, YoloDetection


@dataclass
class RoofAnalysisResult:
    """Complete roof analysis from AI + geometry processing"""
    roof_type: RoofType
    complexity: RoofComplexity
    total_area_sqft: float
    slope_factor: float
    
    # Edge measurements
    ridge_length_ft: float
    hip_length_ft: float
    valley_length_ft: float
    eave_length_ft: float
    rake_length_ft: float
    
    # Features detected
    openings: List[Dict]  # skylights, chimneys, hatches
    penetrations: List[Dict]  # vents, pipes
    
    # Material recommendations
    recommended_waste_pct: float
    estimated_squares: float
    complexity_factors: Dict[str, bool]


class RoofTypeClassifier:
    """Intelligent roof type detection from geometry and AI"""
    
    @staticmethod
    def classify_from_geometry(roof_planes: List[Dict], edges: List[Dict]) -> RoofType:
        """Classify roof type based on geometric analysis"""
        num_planes = len(roof_planes)
        
        # Count edge types
        ridge_count = sum(1 for e in edges if e.get('type') == 'ridge')
        hip_count = sum(1 for e in edges if e.get('type') == 'hip')
        valley_count = sum(1 for e in edges if e.get('type') == 'valley')
        
        # Decision logic based on geometry
        if num_planes <= 2 and ridge_count <= 1 and hip_count == 0:
            if ridge_count == 0:
                return RoofType.FLAT if num_planes == 1 else RoofType.SHED
            return RoofType.GABLE
            
        elif hip_count > 0 and ridge_count <= 1:
            return RoofType.HIP
            
        elif valley_count > 2 or num_planes > 6:
            return RoofType.COMPLEX
            
        elif ridge_count > 2:
            return RoofType.COMPLEX
            
        else:
            return RoofType.GABLE  # Default fallback
    
    @staticmethod
    def assess_complexity(roof_type: RoofType, edges: List[Dict], openings: List[Dict], 
                         penetrations: List[Dict], pitch_factor: float) -> RoofComplexity:
        """Assess roof complexity for waste factor calculation"""
        
        complexity_score = 0
        
        # Base score by type
        complexity_scores = {
            RoofType.FLAT: 1,
            RoofType.SHED: 2, 
            RoofType.GABLE: 3,
            RoofType.HIP: 4,
            RoofType.MANSARD: 6,
            RoofType.GAMBREL: 6,
            RoofType.COMPLEX: 8
        }
        complexity_score += complexity_scores.get(roof_type, 5)
        
        # Add for multiple valleys/hips
        valley_count = sum(1 for e in edges if e.get('type') == 'valley')
        hip_count = sum(1 for e in edges if e.get('type') == 'hip')
        complexity_score += valley_count * 2 + hip_count
        
        # Add for openings and penetrations
        complexity_score += len(openings) * 2
        complexity_score += len(penetrations)
        
        # Add for steep pitch (> 8/12 = 0.67 slope)
        if pitch_factor > 1.2:  # Steep roof
            complexity_score += 3
        
        # Classify based on total score
        if complexity_score <= 4:
            return RoofComplexity.SIMPLE
        elif complexity_score <= 8:
            return RoofComplexity.MEDIUM
        elif complexity_score <= 12:
            return RoofComplexity.COMPLEX
        else:
            return RoofComplexity.VERY_COMPLEX


class RoofFeatureDetector:
    """Enhanced YOLO detection for roof-specific features"""
    
    def __init__(self):
        self.yolo_detector = yolo_detector
        
        # Enhanced class mappings for roof features
        self.roof_opening_classes = {
            'skylight', 'chimney', 'roof_hatch', 'large_vent'
        }
        
        self.roof_penetration_classes = {
            'plumbing_vent', 'hvac_vent', 'exhaust_fan', 'solar_pipe', 'small_vent'
        }
        
        self.roof_edge_classes = {
            'ridge', 'hip', 'valley', 'eave', 'rake'
        }
    
    def detect_roof_features(self, image: np.ndarray, scale_ft_per_px: float) -> Dict:
        """Comprehensive roof feature detection"""
        
        # Run YOLO detection
        detections = self.yolo_detector.detect_objects(image)
        
        openings = []
        penetrations = []
        edges = []
        
        for detection in detections:
            if detection.class_name in self.roof_opening_classes:
                opening = self._process_opening_detection(detection, scale_ft_per_px)
                openings.append(opening)
                
            elif detection.class_name in self.roof_penetration_classes:
                penetration = self._process_penetration_detection(detection, scale_ft_per_px)
                penetrations.append(penetration)
                
            elif detection.class_name in self.roof_edge_classes:
                edge = self._process_edge_detection(detection, scale_ft_per_px)
                edges.append(edge)
        
        return {
            'openings': openings,
            'penetrations': penetrations, 
            'edges': edges
        }
    
    def _process_opening_detection(self, detection: YoloDetection, scale: float) -> Dict:
        """Process roof opening (skylight, chimney, etc.)"""
        # Convert YOLO bbox to real measurements
        width_ft = (detection.bbox.width * scale)
        height_ft = (detection.bbox.height * scale)
        area_sqft = width_ft * height_ft
        perimeter_ft = 2 * (width_ft + height_ft)
        
        return {
            'type': detection.class_name,
            'bbox_norm': {
                'x': detection.bbox.center_x,
                'y': detection.bbox.center_y,
                'width': detection.bbox.width,
                'height': detection.bbox.height
            },
            'measurements': {
                'width_ft': round(width_ft, 2),
                'height_ft': round(height_ft, 2),
                'area_sqft': round(area_sqft, 2),
                'perimeter_ft': round(perimeter_ft, 2),
                'flashing_perimeter_ft': round(perimeter_ft * 1.1, 2)  # 10% extra for overlap
            },
            'confidence': detection.confidence
        }
    
    def _process_penetration_detection(self, detection: YoloDetection, scale: float) -> Dict:
        """Process small roof penetration (vent, pipe, etc.)"""
        # Assume circular penetrations, estimate diameter from bbox
        avg_size_px = (detection.bbox.width + detection.bbox.height) / 2
        diameter_ft = avg_size_px * scale
        diameter_inches = diameter_ft * 12
        
        return {
            'type': detection.class_name,
            'centroid_norm': {
                'x': detection.bbox.center_x,
                'y': detection.bbox.center_y
            },
            'measurements': {
                'diameter_ft': round(diameter_ft, 2),
                'diameter_inches': round(diameter_inches, 1),
            },
            'materials': {
                'requires_boot': True,
                'requires_flashing': True,
                'requires_sealant': True
            },
            'confidence': detection.confidence
        }
    
    def _process_edge_detection(self, detection: YoloDetection, scale: float) -> Dict:
        """Process roof edge (ridge, hip, valley, etc.)"""
        # Estimate length from bbox diagonal or width (depending on edge type)
        if detection.class_name in ['ridge', 'valley']:
            # Usually horizontal or angled lines
            length_ft = max(detection.bbox.width, detection.bbox.height) * scale
        else:
            # Hip/rake might be diagonal
            length_ft = math.sqrt(detection.bbox.width**2 + detection.bbox.height**2) * scale
        
        return {
            'type': detection.class_name,
            'bbox_norm': {
                'x': detection.bbox.center_x,
                'y': detection.bbox.center_y,
                'width': detection.bbox.width,
                'height': detection.bbox.height
            },
            'measurements': {
                'length_ft': round(length_ft, 2),
            },
            'confidence': detection.confidence
        }


class ProfessionalRoofAnalyzer:
    """Main roof analysis engine combining AI detection with geometric processing"""
    
    def __init__(self):
        self.feature_detector = RoofFeatureDetector()
        self.type_classifier = RoofTypeClassifier()
    
    def analyze_roof_plan(self, image: np.ndarray, roof_planes: List[Dict], 
                         scale_ft_per_px: float, assumed_pitch: float = 6.0) -> RoofAnalysisResult:
        """Complete professional roof analysis"""
        
        # Detect all roof features using AI
        detected_features = self.feature_detector.detect_roof_features(image, scale_ft_per_px)
        
        # Calculate pitch factor
        pitch_factor = self._calculate_pitch_factor(assumed_pitch)
        
        # Calculate total roof area
        total_flat_area = sum(plane.get('area_sqft', 0) for plane in roof_planes)
        total_sloped_area = total_flat_area * pitch_factor
        
        # Classify roof type and complexity
        roof_type = self.type_classifier.classify_from_geometry(roof_planes, detected_features['edges'])
        complexity = self.type_classifier.assess_complexity(
            roof_type, detected_features['edges'], 
            detected_features['openings'], detected_features['penetrations'], 
            pitch_factor
        )
        
        # Calculate edge lengths
        edge_lengths = self._calculate_edge_lengths(detected_features['edges'], roof_planes, scale_ft_per_px)
        
        # Determine waste factor based on complexity
        waste_factors = {
            RoofComplexity.SIMPLE: 5.0,
            RoofComplexity.MEDIUM: 8.0,
            RoofComplexity.COMPLEX: 10.0,
            RoofComplexity.VERY_COMPLEX: 15.0
        }
        
        return RoofAnalysisResult(
            roof_type=roof_type,
            complexity=complexity,
            total_area_sqft=total_sloped_area,
            slope_factor=pitch_factor,
            
            ridge_length_ft=edge_lengths['ridge'],
            hip_length_ft=edge_lengths['hip'],
            valley_length_ft=edge_lengths['valley'],
            eave_length_ft=edge_lengths['eave'],
            rake_length_ft=edge_lengths['rake'],
            
            openings=detected_features['openings'],
            penetrations=detected_features['penetrations'],
            
            recommended_waste_pct=waste_factors[complexity],
            estimated_squares=round(total_sloped_area / 100, 2),
            complexity_factors={
                'steep_roof': pitch_factor > 1.2,
                'multiple_valleys': len([e for e in detected_features['edges'] if e.get('type') == 'valley']) > 2,
                'many_penetrations': len(detected_features['penetrations']) > 5,
                'large_openings': len(detected_features['openings']) > 2
            }
        )
    
    def _calculate_pitch_factor(self, rise_per_12: float) -> float:
        """Calculate roof area multiplier from pitch"""
        # rise_per_12 is rise in inches per 12 inches of run
        # pitch_factor = sqrt(rise² + 12²) / 12
        return math.sqrt(rise_per_12**2 + 144) / 12
    
    def _calculate_edge_lengths(self, detected_edges: List[Dict], 
                               roof_planes: List[Dict], scale_ft_per_px: float) -> Dict[str, float]:
        """Calculate total length for each edge type"""
        edge_totals = {
            'ridge': 0.0,
            'hip': 0.0, 
            'valley': 0.0,
            'eave': 0.0,
            'rake': 0.0
        }
        
        for edge in detected_edges:
            edge_type = edge.get('type')
            if edge_type in edge_totals:
                edge_totals[edge_type] += edge['measurements']['length_ft']
        
        # If no edges detected, estimate from roof plane geometry
        if all(length == 0 for length in edge_totals.values()):
            edge_totals = self._estimate_edges_from_planes(roof_planes)
        
        return edge_totals
    
    def _estimate_edges_from_planes(self, roof_planes: List[Dict]) -> Dict[str, float]:
        """Estimate edge lengths when not detected by AI"""
        # Simplified estimation based on plane count and total perimeter
        total_perimeter = sum(plane.get('perimeter_ft', 0) for plane in roof_planes)
        
        if len(roof_planes) <= 2:
            # Simple gable or shed
            return {
                'ridge': total_perimeter * 0.3,  # ~30% ridge
                'eave': total_perimeter * 0.6,   # ~60% eave  
                'rake': total_perimeter * 0.1,   # ~10% rake
                'hip': 0.0,
                'valley': 0.0
            }
        else:
            # Complex roof
            return {
                'ridge': total_perimeter * 0.2,
                'eave': total_perimeter * 0.4,
                'rake': total_perimeter * 0.1,
                'hip': total_perimeter * 0.2,
                'valley': total_perimeter * 0.1
            }