"""Professional Roofing API Endpoints
Enhanced roofing takeoff with AI analysis
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.page import Page
from app.models.roof import Roof, RoofPlane, RoofEdge, RoofOpening, RoofPenetration
from app.schemas.roofing import (
    RoofCreate, RoofRead, RoofUpdate,
    RoofPlaneCreate, RoofPlaneRead, 
    RoofAnalysisRequest, RoofAnalysisResponse,
    RoofTakeoffRequest, RoofTakeoffResponse
)
from app.ai.roof_analyzer import ProfessionalRoofAnalyzer
from app.trades.roofing import EnhancedRoofingEngine

router = APIRouter()


@router.post("/analyze", response_model=RoofAnalysisResponse)
async def analyze_roof_plan(
    request: RoofAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> RoofAnalysisResponse:
    """Comprehensive AI-powered roof analysis"""
    
    # Get the page and its image
    page = db.query(Page).filter(Page.id == request.page_id).first()
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found"
        )
    
    # Initialize AI analyzer
    roof_analyzer = ProfessionalRoofAnalyzer()
    
    # Load page image (you'll need to implement image loading)
    # image = load_page_image(page.file_path)
    
    # For now, simulate analysis with mock data
    # In production, you would run: 
    # analysis = roof_analyzer.analyze_roof_plan(image, request.roof_planes, request.scale_ft_per_px, request.assumed_pitch)
    
    # Mock response
    return RoofAnalysisResponse(
        page_id=request.page_id,
        roof_type="gable",
        complexity="medium", 
        total_area_sqft=2850.0,
        slope_factor=1.12,
        ridge_length_ft=45.0,
        hip_length_ft=0.0,
        valley_length_ft=0.0,
        eave_length_ft=180.0,
        rake_length_ft=54.0,
        openings=[],
        penetrations=[],
        recommended_waste_pct=8.0,
        estimated_squares=28.5,
        complexity_factors={
            "steep_roof": False,
            "multiple_valleys": False,
            "many_penetrations": False,
            "large_openings": False
        }
    )


@router.post("/takeoff", response_model=RoofTakeoffResponse)
async def calculate_roofing_takeoff(
    request: RoofTakeoffRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> RoofTakeoffResponse:
    """Calculate comprehensive roofing material takeoff"""
    
    # Get page and related data
    page = db.query(Page).filter(Page.id == request.page_id).first()
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found"
        )
    
    # Initialize enhanced roofing engine
    roofing_engine = EnhancedRoofingEngine()
    
    # Get rooms and walls for the page
    rooms = page.rooms
    walls = page.walls
    
    # Create mock trade config (in production, get from database)
    from app.models.trade import TradeConfig
    config = TradeConfig(
        coverage_rates={
            "bundle_coverage_sqft": 33.3,  # Standard 3-bundle square coverage
            "starter_ft_per_bundle": 105,  # Linear feet per starter bundle
            "assumed_pitch_rise_per_12": request.pitch_rise or 6.0,
            "underlayment_roll_coverage_sqft": 400,
            "ice_shield_ft_per_roll": 75,
            "ridge_cap_ft_per_bundle": 33,
            "drip_edge_ft_per_piece": 10,
            "valley_flashing_ft_per_piece": 10,
            "nails_per_shingle_bundle": 320,
            "nails_per_box": 7200
        },
        material_unit_costs={
            "shingle_bundle": 45.0,
            "starter_bundle": 35.0,
            "underlayment_roll": 85.0,
            "ice_shield_roll": 125.0,
            "ridge_cap_bundle": 55.0,
            "drip_edge_piece": 12.0,
            "valley_flashing_piece": 18.0,
            "step_flashing_piece": 2.5,
            "pipe_boot": 15.0,
            "nail_box": 85.0,
            "roofing_cement_tube": 8.0,
            "roofing_labor_hour": 65.0
        },
        waste_factor_pct=request.waste_factor_pct or 8.0
    )
    
    # Calculate takeoff
    result = roofing_engine.calculate(rooms, walls, config)
    
    return RoofTakeoffResponse(
        page_id=request.page_id,
        line_items=[
            {
                "description": item.description,
                "unit": item.unit,
                "quantity": item.quantity,
                "unit_cost": item.unit_cost,
                "total_cost": item.total_cost
            }
            for item in result.line_items
        ],
        material_total=result.material_total,
        labor_total=result.labor_total,
        total_cost=result.total_cost,
        metadata=result.metadata
    )


@router.post("/", response_model=RoofRead)
async def create_roof(
    roof: RoofCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> RoofRead:
    """Create a new roof record"""
    
    # Verify page exists
    page = db.query(Page).filter(Page.id == roof.page_id).first()
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found"
        )
    
    db_roof = Roof(**roof.dict())
    db.add(db_roof)
    db.commit()
    db.refresh(db_roof)
    
    return RoofRead.from_orm(db_roof)


@router.get("/{roof_id}", response_model=RoofRead)
async def get_roof(
    roof_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> RoofRead:
    """Get roof by ID"""
    
    roof = db.query(Roof).filter(Roof.id == roof_id).first()
    if not roof:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roof not found"
        )
    
    return RoofRead.from_orm(roof)


@router.get("/page/{page_id}", response_model=List[RoofRead])
async def get_roofs_by_page(
    page_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[RoofRead]:
    """Get all roofs for a page"""
    
    roofs = db.query(Roof).filter(Roof.page_id == page_id).all()
    return [RoofRead.from_orm(roof) for roof in roofs]


@router.put("/{roof_id}", response_model=RoofRead)
async def update_roof(
    roof_id: int,
    roof_update: RoofUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> RoofRead:
    """Update roof"""
    
    roof = db.query(Roof).filter(Roof.id == roof_id).first()
    if not roof:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roof not found"
        )
    
    for field, value in roof_update.dict(exclude_unset=True).items():
        setattr(roof, field, value)
    
    db.commit()
    db.refresh(roof)
    
    return RoofRead.from_orm(roof)


@router.delete("/{roof_id}")
async def delete_roof(
    roof_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete roof"""
    
    roof = db.query(Roof).filter(Roof.id == roof_id).first()
    if not roof:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roof not found"
        )
    
    db.delete(roof)
    db.commit()
    
    return {"message": "Roof deleted successfully"}