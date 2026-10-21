"""Termos de empréstimo e locação: apresentação sem mudanças no banco."""
import io
import os
from datetime import datetime
from decimal import Decimal
from html import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
)


def _register_fonts():
    """Busca fontes presentes no sistema sem distribuí-las no projeto."""
    candidates = [
        ('C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialbd.ttf'),
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
         '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
    ]
    for normal, bold in candidates:
        if os.path.isfile(normal) and os.path.isfile(bold):
            try:
                pdfmetrics.registerFont(TTFont('WMS-Regular', normal))
                pdfmetrics.registerFont(TTFont('WMS-Bold', bold))
                pdfmetrics.registerFontFamily('WMS-Regular', normal='WMS-Regular', bold='WMS-Bold')
                return 'WMS-Regular', 'WMS-Bold'
            except Exception:
                continue
    return 'Helvetica', 'Helvetica-Bold'


def _text(value):
    return escape(str(value).strip() if value is not None and str(value).strip() else '-')


def _date(value):
    return value.strftime('%d/%m/%Y %H:%M') if value else '-'


def _money(value):
    amount = Decimal(value or 0)
    return f"R$ {amount:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def generate_loan_term(loan, company_name):
    """Gera termo multipágina com informações e condições de uso."""
    normal, bold = _register_fonts()
    title_style = ParagraphStyle('TitleWMS', fontName=bold, fontSize=14, leading=18, textColor=colors.HexColor('#164e3b'), alignment=TA_CENTER, spaceAfter=12)
    section_style = ParagraphStyle('SectionWMS', fontName=bold, fontSize=10, leading=14, textColor=colors.HexColor('#164e3b'), spaceBefore=11, spaceAfter=6)
    regular_style = ParagraphStyle('RegularWMS', fontName=normal, fontSize=9, leading=13, alignment=TA_LEFT, spaceAfter=5)
    small_style = ParagraphStyle('SmallWMS', fontName=normal, fontSize=8, leading=11)
    caption_style = ParagraphStyle('CaptionWMS', fontName=bold, fontSize=8, leading=11)
    story = []
    P = lambda val, style=regular_style: Paragraph(_text(val), style)
    # Texto confiável de cláusulas; os dados pessoais usam sempre escape.
    para = lambda raw: Paragraph(raw, regular_style)
    def section(label):
        story.append(Paragraph(escape(label), section_style))
    def detail_table(rows):
        content = [[P(key, caption_style), P(val, small_style)] for key, val in rows]
        t = Table(content, colWidths=[47*mm, 137*mm], hAlign='LEFT')
        t.setStyle(TableStyle([
            ('VALIGN', (0,0),(-1,-1),'TOP'),
            ('ROWBACKGROUNDS',(0,0),(-1,-1),[colors.white, colors.HexColor('#f3f6f4')]),
            ('LINEBELOW',(0,0),(-1,-1),0.3,colors.HexColor('#d8e1db')),
            ('LEFTPADDING',(0,0),(-1,-1),7), ('RIGHTPADDING',(0,0),(-1,-1),7),
            ('TOPPADDING',(0,0),(-1,-1),5), ('BOTTOMPADDING',(0,0),(-1,-1),5),
        ]))
        # Não separar a tabela de seu título entre páginas.
        if story and isinstance(story[-1], Paragraph) and story[-1].style == section_style:
            heading = story.pop()
            story.append(KeepTogether([heading, t]))
        else:
            story.append(t)

    b = io.BytesIO()
    doc = SimpleDocTemplate(b, pagesize=A4, rightMargin=14*mm, leftMargin=14*mm,
                            topMargin=18*mm, bottomMargin=19*mm,
                            title=f'Termo de responsabilidade {loan.id}', author=str(company_name))
    story.append(Paragraph('TERMO DE RESPONSABILIDADE E ' + ('LOCAÇÃO' if loan.kind == 'RENTAL' else 'EMPRÉSTIMO'), title_style))
    story.append(P(f"{company_name}  |  Termo nº {loan.id}  |  Emitido em {_date(datetime.now())}"))
    story.append(HRFlowable(width='100%', thickness=1.3, color=colors.HexColor('#164e3b')))

    section('1. Identificação das partes')
    detail_table([
        ('Cedente / Empresa', company_name),
        ('Responsável / Recebedor', loan.party.name),
        ('Documento / Matrícula', loan.party.document),
        ('E-mail', loan.party.email),
        ('Telefone', loan.party.phone),
        ('Solicitado por', loan.requested_by.name if loan.requested_by else '-'),
        ('Aprovado por', loan.approved_by.name if loan.approved_by else 'Aguardando aprovação'),
    ])
    section('2. Identificação e destino do equipamento')
    detail_table([
        ('Equipamento / Modelo', loan.asset.item.name),
        ('Patrimônio / Etiqueta', loan.asset.asset_tag),
        ('Nº de série', loan.asset.serial_number),
        ('Filial', loan.asset.branch.name if loan.asset.branch else '-'),
        ('Depósito de origem', loan.asset.warehouse.name if loan.asset.warehouse else '-'),
        ('Condição registrada', {'GOOD': 'A classificar (legado)', 'NEW': 'Novo', 'USED': 'Usado', 'DISPOSAL': 'Descarte', 'FAIR': 'A classificar (legado)', 'DAMAGED': 'Danificado', 'MAINTENANCE': 'Em manutenção'}.get(loan.asset.condition, loan.asset.condition)),
    ])
    section('3. Prazo, modalidade e situação')
    status = {'PENDING':'Aguardando aprovação', 'ACTIVE':'Em posse do responsável', 'RETURNED':'Devolvido', 'REJECTED':'Recusado'}.get(loan.status, loan.status)
    detail_table([
        ('Modalidade', 'Locação' if loan.kind=='RENTAL' else 'Empréstimo'),
        ('Situação atual', status),
        ('Data da solicitação', _date(loan.requested_at)),
        ('Data da entrega / início', _date(loan.start_at)),
        ('Devolução prevista', _date(loan.due_at)),
        ('Data efetiva da devolução', _date(loan.returned_at)),
        ('Condição na devolução', {'GOOD': 'Bom', 'NEW': 'Novo', 'FAIR': 'Regular', 'DAMAGED': 'Danificado'}.get(loan.return_condition, loan.return_condition)),
    ])
    section('4. Valores e observações')
    detail_table([
        ('Valor diário', _money(loan.daily_rate) if loan.kind=='RENTAL' else 'Sem cobrança de diária'),
        ('Multa diária por atraso', _money(loan.late_fee_daily)),
        ('Desconto', _money(loan.discount)),
        ('Total calculado até a emissão', _money(loan.total)),
        ('Pagamentos registrados', _money(loan.paid_amount)),
        ('Saldo em aberto', _money(max(Decimal(0),loan.total-Decimal(loan.paid_amount or 0)))),
        ('Observações do registro', loan.notes),
    ])

    section('5. Condições de responsabilidade e devolução')
    clauses = [
        'O responsável compromete-se a utilizar o equipamento para a finalidade autorizada, zelando por sua integridade e conservação.',
        'O equipamento não deve ser transferido a terceiros sem autorização da empresa. Perdas, avarias ou falhas devem ser comunicadas à área responsável.',
        'O responsável deverá devolver o bem e seus acessórios até a data prevista, permitindo a conferência de identificação e condições no ato da devolução.',
        'Em locações, os valores diários e eventuais encargos por atraso seguem os valores registrados acima. A apuração definitiva é realizada na devolução.',
        'A assinatura de recebimento confirma a entrega física do equipamento na data preenchida abaixo. A emissão deste documento, isoladamente, não comprova a entrega.',
    ]
    for idx, clause in enumerate(clauses, 1):
        story.append(para(f'{idx}. {escape(clause)}'))

    section('6. Registro de entrega e assinaturas')
    story.append(P('Local e data da entrega: __________________________________________________________'))
    story.append(Spacer(1, 12*mm))
    signatures = Table([
        ['__________________________________', '__________________________________'],
        [P('Responsável / Recebedor', small_style), P('Representante da empresa', small_style)],
    ], colWidths=[92*mm, 92*mm])
    signatures.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.append(KeepTogether(signatures))
    story.append(Spacer(1, 7*mm))
    story.append(P('Conferência na devolução — data, condição e observações: ______________________________________________'))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#d8e1db'))
        canvas.line(14*mm, 15*mm, A4[0]-14*mm, 15*mm)
        canvas.setFont(normal, 8)
        canvas.drawString(14*mm, 10*mm, str(company_name)[:65])
        canvas.drawRightString(A4[0]-14*mm, 10*mm, f'Termo {loan.id} · Página {doc.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    b.seek(0)
    return b
