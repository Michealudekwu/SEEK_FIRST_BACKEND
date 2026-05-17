from pydantic import BaseModel

class StartRequest(BaseModel):
    symptoms : str

class CompleteRequest(BaseModel):
    structured_symptoms : dict
    questions : list
    answers : str

class DoctorsReportRequest(BaseModel):
    result : dict