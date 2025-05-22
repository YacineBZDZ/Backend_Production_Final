from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

from database.session import get_db
from models.user import User, PrivacyPolicy, UserPrivacyAcceptance
from services.auth import get_current_active_user

# Create router with tags
router = APIRouter(tags=["Privacy Policy"])
public_router = APIRouter(tags=["Public Privacy Policy"])

# Pydantic models for request/response
class PrivacyPolicyResponse(BaseModel):
    id: int
    version: str
    content: str
    summary: Optional[str] = None
    effective_date: datetime
    created_at: datetime
    is_active: bool

    class Config:
        orm_mode = True

class PrivacyPolicyCreate(BaseModel):
    version: str
    content: str
    summary: Optional[str] = None
    effective_date: datetime
    is_active: bool = True

class PrivacyPolicyAcceptance(BaseModel):
    version: str

class PrivacyPolicyStatus(BaseModel):
    accepted: bool
    current_version: Optional[str] = None
    accepted_date: Optional[datetime] = None
    latest_version: Optional[str] = None
    needs_acceptance: bool

# Public endpoint to get the latest active privacy policy
@public_router.get("/latest", response_model=PrivacyPolicyResponse)
def get_latest_policy(db: Session = Depends(get_db)):
    """Get the latest active privacy policy"""
    
    policy = db.query(PrivacyPolicy).filter(
        PrivacyPolicy.is_active == True
    ).order_by(PrivacyPolicy.effective_date.desc()).first()
    
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="No active privacy policy found"
        )
    
    return policy

# Endpoint for users to accept the privacy policy
@router.post("/accept", status_code=status.HTTP_200_OK)
def accept_privacy_policy(
    acceptance: PrivacyPolicyAcceptance,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Endpoint for users to accept the privacy policy"""
    
    # Check if the policy version exists
    policy = db.query(PrivacyPolicy).filter(
        PrivacyPolicy.version == acceptance.version,
        PrivacyPolicy.is_active == True
    ).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Privacy policy version not found")
    
    # Update the user's privacy policy acceptance status
    current_user.privacy_policy_accepted = True
    current_user.privacy_policy_version = acceptance.version
    current_user.privacy_policy_accepted_date = datetime.utcnow()
    
    # Create acceptance record
    acceptance_record = UserPrivacyAcceptance(
        user_id=current_user.id,
        policy_id=policy.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    
    db.add(acceptance_record)
    db.commit()
    
    return {"message": "Privacy policy accepted successfully"}

# Endpoint to get the current user's privacy policy status
@router.get("/status", response_model=PrivacyPolicyStatus)
def get_privacy_policy_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get the current user's privacy policy acceptance status"""
    
    # Get the latest policy version
    latest_policy = db.query(PrivacyPolicy).filter(
        PrivacyPolicy.is_active == True
    ).order_by(PrivacyPolicy.effective_date.desc()).first()
    
    needs_acceptance = False
    if latest_policy:
        if not current_user.privacy_policy_accepted:
            needs_acceptance = True
        elif current_user.privacy_policy_version != latest_policy.version:
            needs_acceptance = True
    
    return {
        "accepted": current_user.privacy_policy_accepted,
        "current_version": current_user.privacy_policy_version,
        "accepted_date": current_user.privacy_policy_accepted_date,
        "latest_version": latest_policy.version if latest_policy else None,
        "needs_acceptance": needs_acceptance
    }

# Admin endpoints to manage privacy policies
@router.post("/admin/create", status_code=status.HTTP_201_CREATED, response_model=PrivacyPolicyResponse)
def create_privacy_policy(
    policy_data: PrivacyPolicyCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new privacy policy version (admin only)"""
    
    # Verify admin role
    if current_user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Only admins can manage privacy policies")
    
    # Check if version already exists
    existing = db.query(PrivacyPolicy).filter(PrivacyPolicy.version == policy_data.version).first()
    if existing:
        raise HTTPException(status_code=400, detail="Privacy policy version already exists")
    
    # Create new policy
    new_policy = PrivacyPolicy(
        version=policy_data.version,
        content=policy_data.content,
        summary=policy_data.summary,
        effective_date=policy_data.effective_date,
        is_active=policy_data.is_active
    )
    
    db.add(new_policy)
    db.commit()
    db.refresh(new_policy)
    
    return new_policy

# Admin endpoint to list all privacy policy versions
@router.get("/admin/all", response_model=List[PrivacyPolicyResponse])
def list_all_policies(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all privacy policy versions (admin only)"""
    
    # Verify admin role
    if current_user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view all privacy policies")
    
    policies = db.query(PrivacyPolicy).order_by(PrivacyPolicy.effective_date.desc()).all()
    return policies

# Admin endpoint to update a privacy policy
@router.put("/admin/{policy_id}", response_model=PrivacyPolicyResponse)
def update_privacy_policy(
    policy_id: int,
    policy_data: PrivacyPolicyCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update an existing privacy policy (admin only)"""
    
    # Verify admin role
    if current_user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Only admins can manage privacy policies")
    
    # Get the policy
    policy = db.query(PrivacyPolicy).filter(PrivacyPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Privacy policy not found")
    
    # Check if version already exists and it's not the current policy
    if policy_data.version != policy.version:
        existing = db.query(PrivacyPolicy).filter(PrivacyPolicy.version == policy_data.version).first()
        if existing:
            raise HTTPException(status_code=400, detail="Privacy policy version already exists")
    
    # Update policy
    policy.version = policy_data.version
    policy.content = policy_data.content
    policy.summary = policy_data.summary
    policy.effective_date = policy_data.effective_date
    policy.is_active = policy_data.is_active
    
    db.commit()
    db.refresh(policy)
    
    return policy

# Public endpoint to get a specific policy version
@public_router.get("/{version}", response_model=PrivacyPolicyResponse)
def get_policy_by_version(
    version: str,
    db: Session = Depends(get_db)
):
    """Get a specific privacy policy by version number"""
    
    policy = db.query(PrivacyPolicy).filter(PrivacyPolicy.version == version).first()
    
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Privacy policy version {version} not found"
        )
    
    return policy