from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from textwrap import wrap
from io import BytesIO

def create_invoice_in_memory(data):
    pdf_buffer = BytesIO()  # Create an in-memory buffer
    c = canvas.Canvas(pdf_buffer, pagesize=letter)

    # Add watermark (faint and centered)
    logo_path = "logo.png"  # Replace with the actual path to your logo file
    try:
        watermark_logo = ImageReader(logo_path)
        c.saveState()
        c.setFillAlpha(0.1)  # Make the watermark faint
        c.drawImage(watermark_logo, 150, 300, width=300, height=300, mask='auto')
        c.restoreState()
    except:
        print("Watermark logo not found. Ensure the logo file is in the specified path.")

    # Add main logo at the top-left
    try:
        main_logo = ImageReader(logo_path)
        c.drawImage(main_logo, 50, 720, width=100, height=50, mask='auto')
    except:
        print("Main logo not found. Ensure the logo file is in the specified path.")

    # Title
    c.setFont("Helvetica-Bold", 20)
    c.drawString(200, 750, "INVOICE")

    # Customer and Delivery Details
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 700, "Customer Details")
    c.drawString(300, 700, "Delivery Details")

    # Customer Details
    c.setFont("Helvetica", 10)
    c.drawString(50, 680, f"Name: {data['name']}")
    c.drawString(50, 665, f"Email: {data['email']}")
    c.drawString(50, 650, f"Phone: {data['number']}")
    c.drawString(50, 635, f"Date: {data['date']}")

    # Delivery Details
    c.setFont("Helvetica", 10)
    c.drawString(300, 680, f"Delivery Company: {data['Delivery Company']}")
    c.drawString(300, 665, f"State: {data['State']}")
    c.drawString(300, 650, f"Location: {data['Location']}")

    # Handle long pickup address
    c.setFont("Helvetica", 10)
    address_lines = wrap(data['Pickup Address'], width=50)
    c.drawString(300, 635, "Pickup Address:")
    y = 620
    for line in address_lines:
        c.drawString(300, y, line)
        y -= 15

    # Order Information
    c.setFont("Helvetica-Bold", 12)
    y -= 15
    c.drawString(50, y, f"Order ID: {data['id']}")

    # Line Separator
    c.line(50, y - 10, 550, y - 10)

    # Add extra space before the table
    y -= 50

    # Table Header
    c.setFillColor(colors.darkblue)
    c.rect(50, y, 500, 20, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y + 5, "NO.")
    c.drawString(100, y + 5, "ITEM")
    c.drawString(250, y + 5, "SIZE")
    c.drawString(350, y + 5, "UNIT PRICE")
    c.drawString(450, y + 5, "TOTAL")

    # Table Data
    c.setFont("Helvetica", 10)
    y -= 30
    for i, item in enumerate(data['items'], start=1):
        # Alternate row colors for readability
        c.setFillColor(colors.whitesmoke if i % 2 == 0 else colors.lightgrey)
        c.rect(50, y, 500, 20, stroke=0, fill=1)
        c.setFillColor(colors.black)
        c.drawString(55, y + 5, str(i))
        c.drawString(100, y + 5, item['name'])
        c.drawString(250, y + 5, item['size'])
        c.drawString(350, y + 5, f" NGN{item['unit_price'] }")
        c.drawString(450, y + 5, f" NGN{item['total'] }")
        y -= 20

    # Line Separator
    c.line(50, y + 10, 550, y + 10)

    # Subtotal, Tax, and Total
    y -= 30
    c.setFont("Helvetica-Bold", 10)
    c.drawString(350, y, "Subtotal:")
    c.drawString(450, y, f" NGN{data['subtotal'] }")
    y -= 15
    c.drawString(350, y, "Tax (10%):")
    c.drawString(450, y, f" NGN{data['tax'] }")
    y -= 15
    c.setFont("Helvetica-Bold", 12)
    c.drawString(350, y, "Total:")
    c.drawString(450, y, f" NGN{data['total']}")

    # Footer
    y -= 40
    c.setFont("Helvetica", 8)
    c.drawString(50, y, "Thank you for choosing D'FOOTPRINT!")
    c.drawString(50, y - 15, "We appreciate your support and look forward to serving you again. Walk with style, always!")

    # Save the PDF to the buffer
    c.save()
    pdf_buffer.seek(0)  # Reset buffer pointer to the beginning
    return pdf_buffer