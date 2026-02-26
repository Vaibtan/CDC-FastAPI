'use client';

import { useState, useEffect } from 'react';
import { Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useDebounce } from '@/hooks/useDebounce';

interface EventFiltersProps {
  tables: string[];
  operations: string[];
  selectedTables: string[];
  selectedOperations: string[];
  searchQuery: string;
  onTableChange: (tables: string[]) => void;
  onOperationChange: (operations: string[]) => void;
  onSearchChange: (query: string) => void;
  onReset: () => void;
}

export function EventFilters({
  tables,
  operations,
  selectedTables,
  selectedOperations,
  searchQuery,
  onTableChange,
  onOperationChange,
  onSearchChange,
  onReset,
}: EventFiltersProps) {
  const [localSearch, setLocalSearch] = useState(searchQuery);
  const debouncedSearch = useDebounce(localSearch, 300);

  // Sync debounced value to parent
  useEffect(() => {
    if (debouncedSearch !== searchQuery) {
      onSearchChange(debouncedSearch);
    }
  }, [debouncedSearch, searchQuery, onSearchChange]);

  // Keep local input in sync with external filter state changes (e.g. reset).
  useEffect(() => {
    if (searchQuery !== localSearch) {
      setLocalSearch(searchQuery);
    }
  }, [searchQuery, localSearch]);

  const hasFilters =
    selectedTables.length > 0 || selectedOperations.length > 0 || searchQuery.length > 0;

  const handleAddTable = (table: string) => {
    if (!selectedTables.includes(table)) {
      onTableChange([...selectedTables, table]);
    }
  };

  const handleRemoveTable = (table: string) => {
    onTableChange(selectedTables.filter((t) => t !== table));
  };

  const handleAddOperation = (operation: string) => {
    if (!selectedOperations.includes(operation)) {
      onOperationChange([...selectedOperations, operation]);
    }
  };

  const handleRemoveOperation = (operation: string) => {
    onOperationChange(selectedOperations.filter((o) => o !== operation));
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-64">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search events..."
            value={localSearch}
            onChange={(e) => setLocalSearch(e.target.value)}
            className="pl-9"
          />
        </div>

        {/* Table Filter */}
        <Select onValueChange={handleAddTable}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Filter by table" />
          </SelectTrigger>
          <SelectContent>
            {tables
              .filter((t) => !selectedTables.includes(t))
              .map((table) => (
                <SelectItem key={table} value={table}>
                  {table}
                </SelectItem>
              ))}
            {tables.length === 0 && (
              <div className="px-2 py-4 text-sm text-muted-foreground text-center">
                No tables available
              </div>
            )}
          </SelectContent>
        </Select>

        {/* Operation Filter */}
        <Select onValueChange={handleAddOperation}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Filter by operation" />
          </SelectTrigger>
          <SelectContent>
            {operations
              .filter((o) => !selectedOperations.includes(o))
              .map((operation) => (
                <SelectItem key={operation} value={operation}>
                  {operation}
                </SelectItem>
              ))}
            {operations.length === 0 && (
              <div className="px-2 py-4 text-sm text-muted-foreground text-center">
                No operations available
              </div>
            )}
          </SelectContent>
        </Select>

        {/* Reset */}
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={onReset}>
            <X className="mr-2 h-4 w-4" />
            Clear
          </Button>
        )}
      </div>

      {/* Active Filters */}
      {(selectedTables.length > 0 || selectedOperations.length > 0) && (
        <div className="flex flex-wrap gap-2">
          {selectedTables.map((table) => (
            <Badge key={table} variant="secondary" className="gap-1">
              {table}
              <button
                onClick={() => handleRemoveTable(table)}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          {selectedOperations.map((operation) => (
            <Badge key={operation} variant="outline" className="gap-1">
              {operation}
              <button
                onClick={() => handleRemoveOperation(operation)}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
