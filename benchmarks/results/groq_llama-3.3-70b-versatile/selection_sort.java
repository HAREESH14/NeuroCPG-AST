import java.util.Scanner;

public class SelectionSort {
    public static void selectionSort(int[] arr, int n) {
        int i, j, minIdx, tmp;
        for (i = 0; i < n - 1; i++) {
            minIdx = i;
            for (j = i + 1; j < n; j++)
                if (arr[j] < arr[minIdx])
                    minIdx = j;
            tmp = arr[minIdx];
            arr[minIdx] = arr[i];
            arr[i] = tmp;
        }
    }

    public static void printArray(int[] arr, int n) {
        for (int i = 0; i < n; i++) System.out.print(arr[i] + " ");
        System.out.println();
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int[] data = new int[100];
        int n, i;
        n = scanner.nextInt();
        if (n > 100) n = 100;
        for (i = 0; i < n; i++) data[i] = scanner.nextInt();
        System.out.print("Original: ");
        printArray(data, n);
        selectionSort(data, n);
        System.out.print("Sorted:   ");
        printArray(data, n);
    }
}