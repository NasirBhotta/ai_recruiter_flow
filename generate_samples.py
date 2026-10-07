"""
Script to generate 3 synthetic CV PDFs for RecruitFlow demonstration and testing.
Uses reportlab to create clean, formatted PDF resumes.
"""

from __future__ import annotations

import os
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas

BASE_DIR = Path(__file__).resolve().parent
SAMPLE_DIR = BASE_DIR / "data" / "sample_cvs"


def create_alice_chen_pdf(output_path: Path) -> None:
    """
    Candidate 1: Alice Chen - Senior Backend Engineer.
    Clean, complete resume with contact details, skills, experience, and degree.
    """
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1e293b"),
    )
    subtitle_style = ParagraphStyle(
        "SubTitleStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#2563eb"),
    )
    contact_style = ParagraphStyle(
        "ContactStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#475569"),
    )
    heading_style = ParagraphStyle(
        "HeadingStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=8,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "BodyStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#334155"),
    )

    story = [
        Paragraph("Alice Chen", title_style),
        Paragraph("Senior Backend Engineer", subtitle_style),
        Paragraph("Email: alice.chen@example.com | Phone: +1-555-0192 | San Francisco, CA | github.com/alicechen", contact_style),
        Spacer(1, 8),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=10),

        Paragraph("PROFESSIONAL SUMMARY", heading_style),
        Paragraph("Senior Backend Engineer with 7+ years of experience designing scalable microservices, distributed architectures, and high-throughput APIs. Proven track record of optimizing database performance and leading engineering teams through major infrastructure transformations.", body_style),
        Spacer(1, 10),

        Paragraph("CORE SKILLS", heading_style),
        Paragraph("<b>Languages & Frameworks:</b> Python, FastAPI, Django, PostgreSQL, Redis, REST APIs<br/>"
                  "<b>Cloud & DevOps:</b> Docker, Kubernetes, AWS, Terraform, CI/CD pipelines, Git<br/>"
                  "<b>Architecture:</b> Distributed Systems, Microservices, Event-Driven Architecture, Caching", body_style),
        Spacer(1, 10),

        Paragraph("WORK EXPERIENCE", heading_style),
        Paragraph("<b>Acme Cloud Solutions</b> — <i>Senior Backend Engineer</i> (2021 – Present)", body_style),
        Paragraph("• Architected core customer-facing APIs handling 25,000 requests/sec with FastAPI and PostgreSQL.<br/>"
                  "• Reduced database query latency by 45% through connection pooling and Redis caching strategies.<br/>"
                  "• Led cross-functional team of 5 backend engineers across microservices deployment on Kubernetes.", body_style),
        Spacer(1, 6),
        Paragraph("<b>NexTech Innovations</b> — <i>Backend Developer</i> (2018 – 2021)", body_style),
        Paragraph("• Developed scalable REST APIs using Python and Django for an enterprise analytics platform.<br/>"
                  "• Automated CI/CD deployment pipelines using Docker and GitHub Actions, cutting release time in half.", body_style),
        Spacer(1, 10),

        Paragraph("EDUCATION", heading_style),
        Paragraph("<b>B.S. in Computer Science</b> — University of California, Berkeley (2014 – 2018)", body_style),
    ]

    doc.build(story)
    print(f"Generated: {output_path}")


def create_bob_miller_pdf(output_path: Path) -> None:
    """
    Candidate 2: Bob Miller - Cloud & DevOps Engineer.
    Intentionally missing phone number, degree, and exact years for several tools.
    """
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1e293b"),
    )
    subtitle_style = ParagraphStyle(
        "SubTitleStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#059669"),
    )
    contact_style = ParagraphStyle(
        "ContactStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#475569"),
    )
    heading_style = ParagraphStyle(
        "HeadingStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=8,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "BodyStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#334155"),
    )

    story = [
        Paragraph("Bob Miller", title_style),
        Paragraph("Cloud & DevOps Engineer", subtitle_style),
        # Notice: NO phone number, NO degree
        Paragraph("Email: bob.miller@example.org | Location: Austin, TX (Remote)", contact_style),
        Spacer(1, 8),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=10),

        Paragraph("OVERVIEW", heading_style),
        Paragraph("Cloud & DevOps Engineer with 4 years of experience focusing on cloud infrastructure automation, container orchestration, and continuous integration. Strong emphasis on reproducible AWS infrastructure.", body_style),
        Spacer(1, 10),

        Paragraph("TECHNICAL SKILLS", heading_style),
        Paragraph("<b>Tools:</b> AWS, Terraform, Docker, CI/CD, Linux, Kubernetes, Bash, GitHub Actions", body_style),
        Spacer(1, 10),

        Paragraph("EXPERIENCE", heading_style),
        Paragraph("<b>DataFlow Infrastructure</b> — <i>DevOps Specialist</i> (2022 – Present)", body_style),
        Paragraph("• Provisioned and maintained multi-region AWS environments using Terraform modules.<br/>"
                  "• Managed containerized services across Kubernetes clusters and monitored system health.<br/>"
                  "• Streamlined build and test workflows with automated GitHub Actions.", body_style),
        Spacer(1, 6),
        Paragraph("<b>CloudOps Labs</b> — <i>Junior Systems Administrator</i> (2020 – 2022)", body_style),
        Paragraph("• Maintained Linux servers, managed user permissions, and monitored cloud costs.<br/>"
                  "• Created bash scripts for backup automation and log rotation.", body_style),
    ]

    doc.build(story)
    print(f"Generated: {output_path}")


def create_charlie_smith_scanned_pdf(output_path: Path) -> None:
    """
    Candidate 3: Charlie Smith - Scanned / Unreadable Resume Simulation.
    Creates an image-only PDF containing a scanned raster image without text OCR,
    causing extract_text() to return empty string and correctly routing to 'Needs Review'.
    """
    from PIL import Image, ImageDraw

    # Generate a raster image of a scanned page
    img_width, img_height = 800, 1100
    img = Image.new("RGB", (img_width, img_height), color="#f8fafc")
    draw = ImageDraw.Draw(img)

    # Draw simulated scanned paper borders and lines
    draw.rectangle([40, 40, img_width - 40, img_height - 40], outline="#94a3b8", width=2)
    draw.rectangle([60, 60, img_width - 60, 140], fill="#e2e8f0")

    # Simulate lines of unreadable scanned text as graphical strokes
    for y in range(180, img_height - 100, 30):
        draw.line([80, y, img_width - 80, y], fill="#cbd5e1", width=3)

    # Scanned red stamp
    draw.rectangle([200, 450, 600, 560], outline="#dc2626", width=4)

    temp_img_path = output_path.parent / "_temp_scanned.png"
    img.save(temp_img_path, format="PNG")

    # Now create the PDF drawing ONLY the image
    c = canvas.Canvas(str(output_path), pagesize=letter)
    width, height = letter
    c.drawImage(str(temp_img_path), 0, 0, width=width, height=height)
    c.showPage()
    c.save()

    if temp_img_path.exists():
        temp_img_path.unlink()

    print(f"Generated (scanned raster): {output_path}")


def generate_all_samples() -> None:
    """Generate all 3 synthetic sample PDFs in the sample directory."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    create_alice_chen_pdf(SAMPLE_DIR / "alice_chen_backend.pdf")
    create_bob_miller_pdf(SAMPLE_DIR / "bob_miller_devops.pdf")
    create_charlie_smith_scanned_pdf(SAMPLE_DIR / "charlie_smith_scanned.pdf")
    print(f"Successfully generated 3 synthetic sample CVs in: {SAMPLE_DIR}")


if __name__ == "__main__":
    generate_all_samples()
