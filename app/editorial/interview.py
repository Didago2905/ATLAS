"""Deterministic persistent interview; all transitions share the inbox transaction."""
from sqlalchemy import select
from pydantic import ValidationError
from app.editorial.models import Interview, ProposalRevision, Asset
from app.editorial.proposal import Proposal, PRICE_KEYS, validate_proposal
from app.editorial import draft_lifecycle

ROLE_NAMES = {'beer_card': 'Ficha de cerveza', 'tap_board': 'Tabla del Tap List', 'label': 'Etiqueta'}
LABELS = {'targets': '¿Qué quieres preparar?', 'existing_beer_id': 'ID de cerveza existente (sin consultar el catálogo)',
          'beer.name': 'Nombre de cerveza', 'beer.brewery': 'Cervecería', 'beer.style': 'Estilo',
          'beer.origin': 'Origen', 'beer.color': 'Color', 'beer.description': 'Descripción',
          'beer.abv': 'ABV, de 0 a 100', 'beer.ibu': 'IBU (opcional, de 0 a 2000)',
          'museum.collection': 'Colección del Museo', 'museum.title': 'Título de la obra',
          'museum.year': 'Año de la obra (opcional)', 'tap_activation_intent': '¿Considerar activación futura? No se ejecutará.',
          'asset': 'Asigna la imagen recibida a un uso. /obra permite adjuntar otra.',
          'subject': '¿Qué representa esta imagen?', 'subject_name': 'Nombre explícito del tema de la imagen',
          'semantic': '¿Añadir un producto semántico del Museo? Es independiente de la cerveza operativa.'}
for key in PRICE_KEYS:
    LABELS['beer.prices.' + key] = 'Precio: ' + key.replace('_', ' ') + ' (opcional; 0 es un precio)'


def latest(db, draft, *, include_inactive=False):
    state = db.get(Interview, draft.id)
    if not include_inactive and state and state.step == 'legacy_pending':
        return None  # Prior proposals are retained, but do not belong to the new legacy intake.
    if not include_inactive and state and isinstance(state.history, dict) and state.history.get('flow') == 'carta_identity':
        return draft_lifecycle.case_latest(db, draft.id, state.history['navigation']['case_id'])
    return db.scalar(select(ProposalRevision).where(ProposalRevision.draft_id == draft.id)
                     .order_by(ProposalRevision.revision.desc()).limit(1))


def plan(p):
    fields = ['targets']
    if set(p.targets) & {'beer_update', 'beer_artwork'}:
        fields.append('existing_beer_id')
    if set(p.targets) & {'beer_create', 'beer_update'}:
        fields += ['beer.' + key for key in ('name', 'brewery', 'style', 'origin', 'color', 'description', 'abv', 'ibu')]
        fields += ['beer.prices.' + key for key in PRICE_KEYS]
        fields += ['tap_activation_intent']
    if 'museum' in p.targets:
        fields += ['museum.collection', 'museum.title', 'museum.year', 'semantic']
        if p.museum.semantic_products:
            fields += ['museum.semantic_products.0.' + key + '.value'
                       for key in ('beer_name', 'beer_style', 'brewery', 'brewery_origin')]
    return fields


def options(step, p):
    if step == 'operation':
        from app.editorial.service import OPERATIONS
        return [(label, code) for code, (label, _) in OPERATIONS.items()]
    if step == 'confirm_operation':
        return [('Confirmar cambio', True), ('Conservar operación', False)]
    if step == 'targets':
        target = {'new': 'beer_create', 'art': 'beer_artwork', 'fix': 'beer_update'}.get(p.operation)
        if target == 'beer_update':
            return [('Corrección de cerveza', [target])]
        if target:
            return [('Solo cerveza', [target]), ('Solo Museo', ['museum']), ('Cerveza y Museo', [target, 'museum'])]
        return [('Museo', ['museum'])]
    if step == 'museum.collection':
        return [('Tablas', 'tap_list'), ('Cartas antiguas', 'carta_vieja'), ('Cartas nuevas', 'carta_nueva'), ('Etiquetas', 'etiquetas')]
    if step == 'tap_activation_intent':
        return [('No', 'no'), ('Considerar después', 'later'), ('Sin decidir', 'unspecified')]
    if step == 'semantic':
        return [('Sin producto por ahora', False), ('Añadir un producto', True)]
    if step == 'asset':
        return [(name, role) for role, name in ROLE_NAMES.items()]
    if step == 'subject':
        return [('Una cerveza', 'beer'), ('Una cervecería', 'brewery'), ('Varias cervezas', 'multiple'), ('No lo sé', 'unknown')]
    if step == 'edit':
        return [(LABELS.get(key, key.replace('museum.semantic_products.0.', 'Producto Museo: ')), key) for key in plan(p)] + [('Cambiar operación', 'operation')]
    return []


def save(db, draft, interview, p, summary):
    p = Proposal.model_validate(p.model_dump())
    draft.prompt_message_id = None  # Previous text replies cannot answer a different question.
    p.revision = interview.revision + 1
    p.change_summary = summary
    p.validated_snapshot()
    interview.revision = p.revision
    db.add(ProposalRevision(draft_id=draft.id, revision=p.revision, payload=p.model_dump(mode='json')))
    db.flush()


def begin(db, draft, operation):
    interview = db.get(Interview, draft.id)
    row = latest(db, draft)
    if row and not isinstance(validate_proposal(row.payload), Proposal):
        raise ValueError("The 2.1 interview cannot edit this proposal contract")
    if row and row.payload['operation'] == operation:
        return interview
    p = Proposal(revision=1, operation=operation)
    if interview is None:
        interview = Interview(id=draft.id, revision=0, step='targets', history=[])
        db.add(interview)
    else:
        interview.step = 'targets'
        draft_lifecycle.set_legacy_steps(interview, [])
    save(db, draft, interview, p, 'Inicio de entrevista; imágenes anteriores conservadas sin asignación automática')
    return interview


def summary(p):
    def show(value):
        if value is None:
            return 'sin indicar'
        return str(value).replace('\n', ' ')[:120]
    lines = [f'Propuesta v{p.revision} · contrato {p.schema_version}', f'Operación: {p.operation}',
             'Destinos: ' + (', '.join(p.targets) or 'sin elegir'), f'Validación: {p.validation_status}']
    if set(p.targets) & {'beer_update', 'beer_artwork'}:
        lines += ['ID propuesto (sin verificar): ' + show(p.existing_beer_id)]
    if set(p.targets) & {'beer_create', 'beer_update'}:
        lines += [f'{LABELS["beer." + key]}: {show(value)}' for key, value in p.beer.model_dump().items() if key != 'prices']
        lines += ['Precios: ' + '; '.join(f'{key}={show(value)}' for key, value in p.beer.prices.model_dump().items())]
    for role, art in p.artworks.model_dump().items():
        if art:
            lines += [f'{ROLE_NAMES[role]}: {art["asset_id"]} · {art["subject"]} · {show(art["subject_name"])}']
    if 'museum' in p.targets:
        lines += [f'Museo: {show(p.museum.collection)} · {show(p.museum.title)} · {show(p.museum.year)}',
                  f'Productos semánticos independientes: {len(p.museum.semantic_products)} (no inferidos)']
        for product in p.museum.semantic_products:
            lines += ['Producto Museo: ' + '; '.join(f'{key}={show(value["value"])} ({value["confidence"]})'
                      for key, value in product.model_dump().items() if key != 'collaborators')]
    lines += [f'Activación futura: {p.tap_activation_intent}', 'Cambio: ' + p.change_summary]
    lines += p.validation_issues
    lines += ['Solo preparación. Nada publicado ni activado. /continuar para retomar; /corregir para editar; /obra para adjuntar.']
    return '\n'.join(lines)


def proposal_summary(payload):
    """Read either contract without routing 2.2 through the legacy state machine."""
    proposal = validate_proposal(payload)
    if isinstance(proposal, Proposal):
        return summary(proposal)
    status = {"incomplete": "Incompleta", "technically_valid": "Validada técnicamente",
              "prepared_for_review": "Preparada para revisión"}[proposal.readiness]
    return (f"Propuesta v{proposal.revision} · contrato 2.2\nEstado: {status}\n"
            f"Identidades: {len(proposal.beers)} · Imágenes: {len(proposal.artworks)} · Acciones propuestas: {len(proposal.actions)}\n"
            "La edición Telegram 2.2 aún no está habilitada. No se ha publicado ni activado nada.")


def render(db, draft):
    interview = db.get(Interview, draft.id)
    p = Proposal.model_validate(latest(db, draft).payload)
    prefix = f'i:{draft.id}:{interview.revision}:'
    def button(label, action):
        return {'text': label, 'callback_data': prefix + action}
    if interview.step == 'summary':
        return summary(p), {'inline_keyboard': [[button('Corregir', 'edit')], [button('Continuar entrevista', 'resume')]]}, None, False
    # subject steps encode their role, never infer it from the operation or image.
    step = interview.step.split(':')[0]
    choices = options(step, p)
    rows = [[button(label, str(index))] for index, (label, _) in enumerate(choices)]
    rows += [[button('Atrás', 'back'), button('Omitir', 'skip')], [button('Ver resumen', 'summary')]]
    text = LABELS.get(step, 'Producto del Museo: ' + step.split('.')[-2] if step.startswith('museum.semantic_products.') else '¿Qué quieres corregir?')
    if step == 'operation':
        text = 'Elige una nueva operación. Se conservarán los datos e imágenes; tendrás que elegir los destinos otra vez.'
    elif step == 'confirm_operation':
        from app.editorial.service import OPERATIONS
        text = '¿Cambiar a «' + OPERATIONS[interview.step.split(':')[1]][0] + '»? No se publicará nada.'
    if not choices:
        text += '\nResponde a este mensaje. Puedes omitir el dato y dejar la propuesta incompleta.'
    else:
        text += '\nElige una opción.'
    text += '\n/cancelar conserva el borrador; /continuar lo retoma.'
    # Inline choices plus ForceReply cannot coexist. Commands and direct replies work with privacy mode.
    return text, {'inline_keyboard': rows}, None, not choices


def set_field(p, path, value):
    data = p.model_dump()
    node = data
    keys = path.split('.')
    for key in keys[:-1]:
        node = node[int(key)] if isinstance(node, list) else node[key]
    node[keys[-1]] = value
    return Proposal.model_validate(data)


def transition(db, draft, action=None, text=None):
    interview = db.get(Interview, draft.id)
    p = Proposal.model_validate(latest(db, draft).payload)
    step = interview.step
    base, _, role = step.partition(':')
    if action in {'summary', 'edit', 'resume', 'back'}:
        if action == 'back':
            history = list(draft_lifecycle.legacy_steps(interview))
            interview.step = history.pop() if history else 'targets'
            draft_lifecycle.set_legacy_steps(interview, history)
        elif action == 'resume':
            history = draft_lifecycle.legacy_steps(interview)
            interview.step = history[-1] if history else 'targets'
        else:
            if step not in {'summary', 'edit'}:
                draft_lifecycle.set_legacy_steps(interview, [*draft_lifecycle.legacy_steps(interview)[-99:], step])
            interview.step = action
        save(db, draft, interview, p, 'Navegación de entrevista')
        return render(db, draft)
    choices = options(base, p)
    if action == 'skip':
        value = None
    elif choices:
        if action is None or not action.isdecimal() or int(action) >= len(choices):
            return render(db, draft)
        value = choices[int(action)][1]
    else:
        if text is None:
            return render(db, draft)
        value = text.strip()
        if base in {'beer.abv', 'beer.ibu', 'museum.year', 'existing_beer_id'} or base.startswith('beer.prices.'):
            try:
                value = int(value) if base in {'museum.year', 'existing_beer_id'} else float(value.replace(',', '.'))
            except ValueError:
                result = render(db, draft)
                return ('Escribe un número válido o usa Omitir.\n' + result[0], *result[1:])
    next_step = None
    try:
        if base == 'operation':
            next_step = 'confirm_operation:' + value if value else 'summary'
        elif base == 'confirm_operation':
            if value:
                p = set_field(p, 'operation', role)
                p = set_field(p, 'targets', [])
                draft_lifecycle.set_legacy_steps(interview, [])
                next_step = 'targets'
            else:
                next_step = 'summary'
        elif base == 'semantic':
            if value and not p.museum.semantic_products:
                from app.editorial.proposal import SemanticProduct
                p.museum.semantic_products = [SemanticProduct()]
            elif not value:
                p.museum.semantic_products = []
        elif base == 'edit':
            next_step = value or 'summary'
        elif base == 'asset':
            if value is None:
                next_step = 'summary'
            else:
                # Source selection was explicitly initiated after receiving an image.
                from app.editorial.models import Version
                version = db.scalar(select(Version).where(Version.draft_id == draft.id, Version.revision == draft.revision))
                if not version or db.get(Asset, version.asset_id) is None:
                    return ('Usa /obra para recibir una imagen antes de asignarla.', None, None, False)
                p = set_field(p, 'artworks.' + value, {'asset_id': version.asset_id, 'subject': 'unknown'})
                next_step = 'subject:' + value
        elif base == 'subject':
            if value is not None:
                p = set_field(p, 'artworks.' + role + '.subject', value)
                p = set_field(p, 'artworks.' + role + '.subject_name', None)
            next_step = 'subject_name:' + role if value in {'beer', 'brewery'} else 'summary'
        elif base == 'subject_name':
            p = set_field(p, 'artworks.' + role + '.subject_name', value)
            next_step = 'summary'
        else:
            if base == 'targets':
                p = set_field(p, base, value or [])
            elif value is not None or base not in {'tap_activation_intent'}:
                p = set_field(p, base, value)
    except (ValidationError, ValueError):
        result = render(db, draft)
        return ('Valor no válido. Revisa el límite indicado; usa un importe finito, de 0 a 1000000.\n' + result[0], *result[1:])
    fields = plan(p)
    if next_step is None:
        index = fields.index(base) if base in fields else len(fields)
        next_step = fields[index + 1] if index + 1 < len(fields) else 'asset'
    draft_lifecycle.set_legacy_steps(interview, [*draft_lifecycle.legacy_steps(interview)[-99:], step])
    interview.step = next_step
    save(db, draft, interview, p, 'Respuesta: ' + base)
    return render(db, draft)
