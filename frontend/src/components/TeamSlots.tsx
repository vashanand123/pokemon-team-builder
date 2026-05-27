import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  arrayMove,
  horizontalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { TeamMember } from '../api/teams'
import { TYPE_COLORS } from '../lib/typeColors'
import { Sprite } from './Sprite'

function Slot({
  id,
  member,
  onRemove,
}: {
  id: string
  member: TeamMember
  onRemove: () => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }
  return (
    <div ref={setNodeRef} style={style} className="relative rounded-xl border border-slate-200 bg-white p-2 text-center shadow-sm transition hover:shadow-md">
      <button
        onClick={onRemove}
        className="absolute -right-1.5 -top-1.5 z-10 h-5 w-5 rounded-full bg-red-500 text-xs leading-none text-white shadow-sm transition hover:bg-red-600 active:scale-90"
        aria-label={`Remove ${member.pokemon.name}`}
      >
        ×
      </button>
      <div {...attributes} {...listeners} className="cursor-grab touch-none">
        <Sprite
          url={member.pokemon.sprite_url}
          name={member.pokemon.name}
          className="mx-auto h-16 w-16 object-contain drop-shadow-sm"
        />
        <div className="truncate text-xs capitalize">{member.pokemon.name.replace(/-/g, ' ')}</div>
        <div className="mt-1 flex flex-wrap justify-center gap-0.5">
          {member.pokemon.types.map((t) => (
            <span
              key={t}
              className={`rounded-full px-1.5 py-px text-[8px] font-semibold uppercase tracking-wide text-white shadow-sm ${
                TYPE_COLORS[t] ?? 'bg-slate-400'
              }`}
            >
              {t}
            </span>
          ))}
        </div>
        <div className="mt-0.5 text-[10px] text-slate-400">
          BST {Object.values(member.pokemon.stats).reduce((a, b) => a + b, 0)}
        </div>
      </div>
    </div>
  )
}

export function TeamSlots({
  members,
  onReorder,
  onRemoveAt,
}: {
  members: TeamMember[]
  onReorder: (ids: number[]) => void
  onRemoveAt: (index: number) => void
}) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))
  const items = members.map((m, i) => `${m.pokemon.id}#${i}`)
  const empties = Array.from({ length: Math.max(0, 6 - members.length) })

  function handleDragEnd(e: DragEndEvent) {
    const { active, over } = e
    if (!over || active.id === over.id) return
    const oldIndex = items.indexOf(String(active.id))
    const newIndex = items.indexOf(String(over.id))
    if (oldIndex < 0 || newIndex < 0) return
    onReorder(arrayMove(members.map((m) => m.pokemon.id), oldIndex, newIndex))
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <div className="grid grid-cols-6 gap-2">
        <SortableContext items={items} strategy={horizontalListSortingStrategy}>
          {members.map((m, i) => (
            <Slot key={items[i]} id={items[i]} member={m} onRemove={() => onRemoveAt(i)} />
          ))}
        </SortableContext>
        {empties.map((_, i) => (
          <div
            key={`empty-${i}`}
            className="flex h-[92px] items-center justify-center rounded-xl border border-dashed border-slate-200 text-xs text-slate-300"
          >
            empty
          </div>
        ))}
      </div>
    </DndContext>
  )
}
