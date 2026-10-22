"""Generates 3 realistic, unlabeled anonymized sample contracts for SlothClerk testing."""
from pathlib import Path
import docx

def create_samples():
    samples_dir = Path("samples")
    samples_dir.mkdir(exist_ok=True)

    # -------------------------------------------------------------
    # 1. Mutual Non-Disclosure Agreement (DOCX) - Realistic & Unlabeled
    # -------------------------------------------------------------
    doc_nda = docx.Document()
    doc_nda.add_heading("MUTUAL NON-DISCLOSURE AGREEMENT", 0)
    doc_nda.add_paragraph("Effective Date: November 15, 2026")
    doc_nda.add_paragraph(
        "This Mutual Confidentiality and Non-Disclosure Agreement ('Agreement') is entered into by and between "
        "Apex Digital Solutions LLC ('Disclosing Party') and Quantum Robotics Inc ('Receiving Party')."
    )
    doc_nda.add_heading("1. Scope of Confidential Information", level=1)
    doc_nda.add_paragraph(
        "Receiving Party shall hold and maintain all Confidential Information in strictest confidence "
        "for a period of five (5) years following disclosure. Receiving Party must not disclose, publish, "
        "or disseminate Confidential Information to any third party without prior written consent."
    )
    doc_nda.add_heading("2. Breach of Covenants and Liquidated Damages", level=1)
    doc_nda.add_paragraph(
        "In the event of an intentional breach or leak of Trade Secrets, Receiving Party shall be liable for "
        "liquidated damages amounting to $150,000 USD per incident, in addition to full attorney fees and legal costs."
    )
    doc_nda.add_heading("3. Termination and Return of Materials", level=1)
    doc_nda.add_paragraph(
        "Upon written notice or termination by December 31, 2027, Receiving Party shall destroy or return all "
        "materials within fourteen (14) business days. Certification of destruction must be provided."
    )
    doc_nda.add_heading("4. Governing Law and Arbitration", level=1)
    doc_nda.add_paragraph(
        "This Agreement is governed by the laws of Delaware. All disputes must be submitted to binding arbitration "
        "in Wilmington, Delaware. The prevailing party is entitled to recover all reasonable attorney costs."
    )
    doc_nda.save(str(samples_dir / "nda_agreement.docx"))

    # -------------------------------------------------------------
    # 2. SaaS Master Services Agreement (DOCX) - Realistic & Unlabeled
    # -------------------------------------------------------------
    doc_saas = docx.Document()
    doc_saas.add_heading("MASTER CLOUD SERVICES AGREEMENT", 0)
    doc_saas.add_paragraph("Execution Date: January 10, 2026")
    doc_saas.add_paragraph(
        "This Master Cloud Services Agreement is entered into between CloudSphere Technologies Corp. ('Provider') "
        "and Stellar Logistics Ltd. ('Customer')."
    )
    doc_saas.add_heading("1. Subscription Terms and Invoicing", level=1)
    doc_saas.add_paragraph(
        "Customer shall pay an Annual Platform Fee of $48,000 USD, billed quarterly in advance at $12,000 USD per quarter. "
        "Invoices are payable Net 30 days. Late payments shall incur a monthly finance penalty of 1.5%."
    )
    doc_saas.add_heading("2. Security Standards and Incident Notification", level=1)
    doc_saas.add_paragraph(
        "Provider will maintain SOC2 Type II compliance. In the event of a verified data breach, Provider must notify Customer "
        "in writing within seventy-two (72) hours. Customer has the right to conduct an annual security audit at Customer's expense."
    )
    doc_saas.add_heading("3. Service Term and Renewal", level=1)
    doc_saas.add_paragraph(
        "The initial service period commences on January 15, 2026 and terminates on January 14, 2028. "
        "This Agreement shall automatically renew for additional consecutive 24-month terms unless Customer "
        "provides written notice of non-renewal at least ninety (90) days prior to the expiration of the current term. "
        "In the event of non-renewal failure within this window, Customer shall remain bound to renewal fees totaling $96,000 USD."
    )
    doc_saas.add_heading("4. Limitation of Liability and General Terms", level=1)
    doc_saas.add_paragraph(
        "Neither party shall be liable for indirect or consequential damages. This Agreement constitutes the complete "
        "understanding between the parties with respect to the subject matter hereof."
    )
    doc_saas.save(str(samples_dir / "saas_msa.docx"))

    # -------------------------------------------------------------
    # 3. Executive Employment and Proprietary Information Agreement (DOCX)
    # -------------------------------------------------------------
    doc_emp = docx.Document()
    doc_emp.add_heading("EXECUTIVE EMPLOYMENT AND PROPRIETARY INFORMATION AGREEMENT", 0)
    doc_emp.add_paragraph("Effective Date: March 1, 2026")
    doc_emp.add_paragraph(
        "This Executive Employment Agreement ('Agreement') is entered into by and between "
        "Vertex BioTech Systems Inc. ('Company') and Dr. Sarah Lin ('Employee')."
    )
    doc_emp.add_heading("1. Position, Duties and Base Compensation", level=1)
    doc_emp.add_paragraph(
        "Employee shall serve as Vice President of Research. Company shall pay Employee an annual base salary "
        "of $175,000 USD, payable bi-weekly in accordance with standard payroll practices. "
        "Employee is eligible for a target annual discretionary performance bonus of $35,000 USD."
    )
    doc_emp.add_heading("2. Signing Bonus and Repayment Clawback", level=1)
    doc_emp.add_paragraph(
        "Company shall pay Employee a one-time signing bonus of $30,000 USD upon the first regular payroll cycle. "
        "In the event Employee resigns or is terminated for Cause within twelve (12) months of Commencement Date, "
        "Employee shall immediately repay 100% of the $30,000 USD signing bonus to Company within thirty (30) days."
    )
    doc_emp.add_heading("3. Proprietary Information and Inventions Assignment", level=1)
    doc_emp.add_paragraph(
        "Employee hereby irrevocably assigns to Company all right, title, and interest in and to all inventions, "
        "developments, designs, and computer code conceived, whether or not during working hours. "
        "Employee must deliver written list of Prior Inventions to Company upon signing."
    )
    doc_emp.add_heading("4. Restrictive Covenants and Non-Compete", level=1)
    doc_emp.add_paragraph(
        "Employee agrees that for twenty-four (24) months following termination of employment for any reason, "
        "Employee shall not directly or indirectly engage in, perform services for, or invest in any competing "
        "business entity worldwide. Employee must return all Company laptops, access badges, and proprietary materials "
        "within forty-eight (48) hours of termination."
    )
    doc_emp.add_heading("5. Dispute Resolution and Arbitration", level=1)
    doc_emp.add_paragraph(
        "All employment disputes must be submitted to binding individual arbitration, and Employee expressly "
        "waives all rights to a jury trial or class action proceeding. Submit Form I-9 verification and signed "
        "employee handbook acknowledgment within three (3) business days of Commencement Date."
    )
    doc_emp.save(str(samples_dir / "employment_agreement.docx"))

    # -------------------------------------------------------------
    # 3. Commercial Office Sublease Agreement (PDF) - 7 Pages Long
    # -------------------------------------------------------------
    pages = [
        # Page 1: Preamble & Premises
        (
            "COMMERCIAL REAL ESTATE SUBLEASE AGREEMENT\n\n"
            "This Sublease Agreement is entered into as of February 1, 2026 by and between\n"
            "Metro Real Estate Holdings LLC ('Sublessor') and Nexa Innovations Corp ('Subtenant').\n\n"
            "RECITALS\n"
            "WHEREAS, Sublessor is the tenant under a prime lease dated January 15, 2024 with 500 Market Landlord LP;\n"
            "WHEREAS, Subtenant desires to sublease a portion of the building described herein.\n\n"
            "ARTICLE 1: DEMISED PREMISES AND TERM\n"
            "1.1 Demised Premises: Sublessor leases to Subtenant Suite 400 located at 500 Market Street, San Francisco, CA.\n"
            "1.2 Term: The initial term commences on March 1, 2026 and terminates promptly on February 28, 2029.\n"
            "1.3 Early Access: Subtenant shall have access five (5) business days prior to commencement solely for staging."
        ),
        # Page 2: Rent & Security Deposit
        (
            "ARTICLE 2: RENT AND SECURITY DEPOSIT\n\n"
            "2.1 Monthly Base Rent: Subtenant agrees to pay base monthly rent of $8,500 USD on the first day of each calendar month.\n"
            "Rent payments shall be made electronically to Sublessor's designated account.\n\n"
            "2.2 Security Deposit: A refundable Security Deposit of $17,000 USD is due upon signing.\n"
            "The deposit shall be held in an interest-bearing escrow account as security for the faithful performance of all covenants.\n\n"
            "2.3 Late Charges: If rent is received after the 5th, a late surcharge of $450 USD will be charged.\n"
            "Said surcharge constitutes agreed administrative damages and not a forfeiture."
        ),
        # Page 3: Use & Alterations
        (
            "ARTICLE 3: USE OF PREMISES AND PERMITTED OPERATIONS\n\n"
            "3.1 Permitted Use: The Demised Premises shall be used exclusively for general executive office purposes\n"
            "and software engineering development, in full compliance with all municipal and state codes.\n\n"
            "ARTICLE 4: ALTERATIONS, FIXTURES AND IMPROVEMENTS\n"
            "4.1 Improvements: Subtenant must obtain prior written approval before installing any structural fixtures.\n"
            "All non-structural cosmetic painting or cabling may proceed upon ten (10) days advance notice to Sublessor.\n"
            "4.2 Mechanics Liens: Subtenant shall promptly discharge any mechanic's lien within fifteen (15) days of filing."
        ),
        # Page 4: Maintenance & Insurance
        (
            "ARTICLE 5: MAINTENANCE AND UTILITIES\n\n"
            "5.1 Sublessor Maintenance: Sublessor shall maintain the building structural elements, common corridors, and elevators.\n"
            "5.2 Subtenant Maintenance: Subtenant shall maintain the interior premises in neat and sanitary condition.\n\n"
            "ARTICLE 6: INSURANCE REQUIREMENTS\n"
            "6.1 Liability Coverage: Subtenant shall maintain commercial general liability insurance of not less than $2,000,000 USD aggregate.\n"
            "6.2 Certificate of Insurance: Subtenant shall deliver a certificate naming Sublessor and Prime Landlord as additional insureds."
        ),
        # Page 5: Assignment & Casualty
        (
            "ARTICLE 7: ASSIGNMENT AND SUBLETTING\n\n"
            "7.1 Consent Required: Subtenant shall not assign or further sublet the Demised Premises without Sublessor's written consent.\n"
            "Sublessor shall not unreasonably withhold, condition, or delay its consent for creditworthy corporate successors.\n\n"
            "ARTICLE 8: CASUALTY AND RESTORATION\n"
            "8.1 Fire and Casualty: In the event of substantial damage rendering the premises unusable for sixty (60) days,\n"
            "either party may terminate this Sublease upon twenty (20) days notice."
        ),
        # Page 6: Repossession & Waivers
        (
            "ARTICLE 9: DEFAULT AND REMEDIES\n\n"
            "9.1 Events of Default: Failure to pay rent within five (5) days of written notice shall constitute an event of default.\n\n"
            "ARTICLE 10: MUNICIPAL ACTIONS AND REPOSSESSION RIGHTS\n"
            "10.1 Special Repossession: Section 14: Sublessor reserves unconditional right to repossess premises upon 7 days notice in the event of municipal zoning revisions without refunding unamortized improvements. Subtenant waives all jury trial rights.\n\n"
            "ARTICLE 11: SURRENDER OF PREMISES\n"
            "11.1 Surrender: Upon expiration or earlier termination, Subtenant shall vacate and yield the Demised Premises broom clean."
        ),
        # Page 7: Boilerplate & Exhibit A
        (
            "ARTICLE 12: GENERAL PROVISIONS\n\n"
            "12.1 Governing Law: This Agreement shall be governed by the laws of the State of California, without regard to conflicts.\n"
            "12.2 Notices: All formal notices shall be sent via certified mail or nationally recognized courier.\n"
            "12.3 Entire Agreement: This Sublease constitutes the entire agreement between the parties.\n\n"
            "EXHIBIT A: DEMISED PREMISES FLOOR PLAN AND SPECIFICATIONS\n"
            "Suite 400 comprises approximately 4,200 rentable square feet located on the fourth floor of 500 Market Street.\n"
            "The space includes six private perimeter offices, two conference rooms, an open collaboration area, and kitchen."
        )
    ]

    pdf_path = samples_dir / "commercial_lease.pdf"
    _generate_multipage_pdf(str(pdf_path), pages)

    print("Created 4 realistic, unlabeled sample contracts:")
    print(" - samples/nda_agreement.docx")
    print(" - samples/saas_msa.docx")
    print(" - samples/employment_agreement.docx")
    print(" - samples/commercial_lease.pdf (7 pages)")


def _generate_multipage_pdf(filename: str, pages_content: list):
    """Generates a valid standard multi-page PDF containing text for each page."""
    num_pages = len(pages_content)
    font_obj_id = num_pages * 2 + 3

    objects = []
    # 1: Catalog
    objects.append((1, b"<< /Type /Catalog /Pages 2 0 R >>"))

    # 2: Pages container
    kids_str = " ".join(f"{3 + i*2} 0 R" for i in range(num_pages))
    objects.append((2, f"<< /Type /Pages /Kids [{kids_str}] /Count {num_pages} >>".encode("ascii")))

    curr_id = 3
    for p_idx, text in enumerate(pages_content):
        content_id = curr_id + 1
        page_obj = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R /Resources << /Font << /F1 {font_obj_id} 0 R >> >> >>".encode("ascii")
        objects.append((curr_id, page_obj))

        lines = text.split("\n")
        text_cmds = ["BT", "/F1 10 Tf", "50 740 Td", "13 TL"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            text_cmds.append(f"({escaped}) Tj")
            text_cmds.append("T*")
        text_cmds.append("ET")
        stream = "\n".join(text_cmds).encode("latin-1", "replace")
        content_obj = f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        objects.append((content_id, content_obj))
        curr_id += 2

    # Font object
    objects.append((font_obj_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))

    with open(filename, "wb") as f:
        f.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = {}
        for obj_id, data in objects:
            offsets[obj_id] = f.tell()
            f.write(f"{obj_id} 0 obj\n".encode("ascii"))
            f.write(data)
            f.write(b"\nendobj\n")

        xref_pos = f.tell()
        total_objs = font_obj_id + 1
        f.write(b"xref\n")
        f.write(f"0 {total_objs}\n".encode("ascii"))
        f.write(b"0000000000 65535 f \n")
        for i in range(1, total_objs):
            off = offsets[i]
            f.write(f"{off:010d} 00000 n \n".encode("ascii"))
        f.write(b"trailer\n")
        f.write(f"<< /Size {total_objs} /Root 1 0 R >>\n".encode("ascii"))
        f.write(b"startxref\n")
        f.write(f"{xref_pos}\n".encode("ascii"))
        f.write(b"%%EOF\n")


if __name__ == "__main__":
    create_samples()
