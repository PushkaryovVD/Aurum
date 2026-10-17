import { useState } from "react";
import { Plus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { GoalList } from "@/components/goals/GoalList";
import { GoalFormModal } from "@/components/goals/GoalFormModal";
import { GoalContributionModal } from "@/components/goals/GoalContributionModal";
import { useDeleteGoal, useGoals } from "@/hooks/useGoals";
import { QueryStateNotice } from "@/components/ui/QueryStateNotice";
import { useTranslation } from "@/lib/i18n";
import { queryDisplayState } from "@/lib/queryDisplayState";
import type { Goal } from "@/types";

export function GoalsPage() {
  const { t } = useTranslation();
  const { data: goals, isLoading, isError } = useGoals();
  const displayState = queryDisplayState(goals !== undefined, isLoading, isError);
  const deleteGoal = useDeleteGoal();

  const [formOpen, setFormOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<Goal | null>(null);
  const [contributionOpen, setContributionOpen] = useState(false);
  const [contributingGoal, setContributingGoal] = useState<Goal | null>(null);

  function openCreateModal() {
    setEditingGoal(null);
    setFormOpen(true);
  }

  function openEditModal(goal: Goal) {
    setEditingGoal(goal);
    setFormOpen(true);
  }

  function openContributionModal(goal: Goal) {
    setContributingGoal(goal);
    setContributionOpen(true);
  }

  function handleDelete(goal: Goal) {
    if (window.confirm(t("goal.confirmDelete", { name: goal.name }))) {
      deleteGoal.mutate(goal.id);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("nav.goals")}</CardTitle>
          <Button onClick={openCreateModal}>
            <Plus size={16} />
            {t("common.add")}
          </Button>
        </CardHeader>
        <CardContent>
          <QueryStateNotice
            state={displayState}
            unavailableText={t("goal.unavailable")}
            staleText={t("goal.stale")}
            className="mb-3"
          />
          {displayState === "loading" ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : displayState === "unavailable" ? null : (
            <GoalList
              items={goals ?? []}
              onContribute={openContributionModal}
              onEdit={openEditModal}
              onDelete={handleDelete}
            />
          )}
        </CardContent>
      </Card>

      <GoalFormModal open={formOpen} onClose={() => setFormOpen(false)} goal={editingGoal} />
      <GoalContributionModal
        open={contributionOpen}
        onClose={() => setContributionOpen(false)}
        goal={contributingGoal}
      />
    </div>
  );
}
