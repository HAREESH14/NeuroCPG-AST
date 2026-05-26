import java.util.Scanner;

public class BinarySearch {
    public static int binarySearch(int[] arr, int n, int target) {
        int left = 0;
        int right = n - 1;
        int mid;

        while (left <= right) {
            mid = (left + right) / 2;

            if (arr[mid] == target) {
                return mid;
            } else if (arr[mid] < target) {
                left = mid + 1;
            } else {
                right = mid - 1;
            }
        }

        return -1;  // Not found
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n, target, i, result;
        int[] arr = new int[100];

        n = scanner.nextInt();
        target = scanner.nextInt();
        if (n > 100) n = 100;

        for (i = 0; i < n; i++) {
            arr[i] = scanner.nextInt();
        }

        System.out.print("Sorted Array: ");
        for (i = 0; i < n; i++) {
            System.out.print(arr[i] + " ");
        }
        System.out.println();

        result = binarySearch(arr, n, target);

        if (result != -1) {
            System.out.println("Target " + target + " found at index " + result);
        } else {
            System.out.println("Target " + target + " not found");
        }

        scanner.close();
    }
}